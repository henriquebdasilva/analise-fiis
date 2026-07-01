"""Relatório mensal completo + resumo executivo (#6).

Migrado do analise_fiis.py original (todo o visual de cards e gráficos preservado),
adaptado para a estrutura modular: usa core/ para util e recebe cfg.
"""
from datetime import datetime

from core.util import _num, _fmt_pct, _fmt_num, _fmt_money, _extrair_json

COR_PRIMARIA = "#1F4E78"
COR_DY = "#2E75B6"
COR_INDEX = "#1E7B46"
COR_PRAZO = "#C77B30"
COR_VAC = "#C0392B"



def montar_prompt(ticker):
    return (
        f"Pesquise dados públicos ATUAIS do fundo imobiliário brasileiro {ticker} "
        f"(relatório gerencial mais recente, Status Invest, Funds Explorer, Fundamentus).\n\n"
        f"Responda APENAS com um objeto JSON válido (sem markdown, sem texto extra), "
        f"com estes campos. Use null quando NÃO tiver certeza — NÃO invente números:\n"
        f"{{\n"
        f'  "descricao": "<descrição breve do fundo em 1 frase: o que é, segmento, gestora>",\n'
        f'  "tipo": "papel|tijolo|hibrido|fof",\n'
        f'  "cota_atual": <preço de fechamento mais recente da cota em reais, '
        f'apenas o número decimal ex 102.50 (este dado é público e quase sempre existe '
        f'no Status Invest — preencha sempre que possível), ou null>,\n'
        f'  "ultimo_dividendo": <valor do último provento/dividendo pago por cota em reais, '
        f'apenas o número decimal ex 0.85 (dado público no Status Invest — preencha sempre '
        f'que possível), ou null>,\n'
        f'  "dy_12m": <decimal ex 0.115 ou null>,\n'
        f'  "pvp": <decimal ex 0.92 ou null>,\n'
        f'  "rentabilidade_12m": <retorno TOTAL do FII nos últimos 12 meses (valorização '
        f'da cota + dividendos), decimal ex 0.14, pode ser negativo (dado público no '
        f'Status Invest — preencha sempre que possível), ou null>,\n'
        f'  "cdi_12m": <CDI acumulado nos últimos 12 meses, decimal ex 0.135 '
        f'(preencha sempre, é um dado macro conhecido), ou null>,\n'
        f'  "ifix_12m": <variação do índice IFIX nos últimos 12 meses, decimal ex 0.09, '
        f'pode ser negativo (dado público), ou null>,\n'
        f'  "vacancia_fisica": <decimal 0-1 ou null se não for tijolo>,\n'
        f'  "receita_locacao_mes": "<receita de locação do último mês com unidade, '
        f'ex: R$ 12,5 mi, ou null se não encontrar/não aplicável>",\n'
        f'  "dy_mensal": [<lista dos últimos 12 meses, do mais antigo ao recente, '
        f'cada item {{"mes":"AAAA-MM","valor":<R$/cota decimal>}} ou [] se não encontrar>],\n'
        f'  "distribuicao_geografica": [<distribuição dos ativos/imóveis por estado ou região, '
        f'cada item {{"regiao":"SP|RJ|MG|Sul|Nordeste|...","pct":<0-1>}}, máximo 6, '
        f'do maior ao menor; [] se não encontrar>],\n'
        f'  "inquilinos": [<principais inquilinos por % da receita imobiliária, para '
        f'fundos de tijolo, cada item {{"nome":"...","pct":<0-1>}}, do maior ao menor, '
        f'máximo 6; [] se não aplicável ou não encontrar>],\n'
        f'  "indexadores": [<distribuição dos contratos/CRIs, cada item '
        f'{{"nome":"IPCA|IGP-M|CDI|Prefixado|Outros","pct":<0-1>}} ou [] se não souber>],\n'
        f'  "prazo_contratos": [<vencimento dos contratos para fundos de tijolo, cada item '
        f'{{"faixa":"Até 2027|2028-2031|Após 2031","pct":<0-1>}} ou [] se não aplicável>],\n'
        f'  "positivos": "<2 pontos positivos curtos separados por ;>",\n'
        f'  "riscos": "<3 a 4 riscos DETALHADOS e específicos deste FII, cada um com '
        f'uma explicação breve do porquê é um risco, separados por ;>",\n'
        f'  "fatos_relevantes": [<comunicados/fatos relevantes ou notícias importantes dos '
        f'últimos 3 meses (ex: nova emissão de cotas, compra/venda de imóvel, mudança de '
        f'gestão, alteração de dividendo, incorporação), cada item '
        f'{{"data":"AAAA-MM ou data","descricao":"resumo em uma frase"}}, máximo 3, '
        f'do mais recente ao mais antigo; [] se não houver nada relevante recente>],\n'
        f'  "sugestao": "Comprar|Manter|Aguardar|Vender"\n'
        f"}}")


def _resumo_executivo(lista_dados):
    """#6 — parágrafo-resumo no topo: contagem, destaques por P/VP e DY."""
    validos = [d for d in lista_dados if d]
    if not validos:
        return ""
    n = len(validos)
    # melhor DY e menor P/VP
    com_dy = [(d.get("_ticker"), _num(d.get("dy_12m"))) for d in validos if _num(d.get("dy_12m")) is not None]
    com_pvp = [(d.get("_ticker"), _num(d.get("pvp"))) for d in validos if _num(d.get("pvp")) is not None]
    partes = [f"Sua carteira tem <strong>{n} FIIs</strong> analisados neste mês."]
    if com_dy:
        t, v = max(com_dy, key=lambda x: x[1])
        partes.append(f"Maior DY: <strong>{t}</strong> ({_fmt_pct(v)}).")
    if com_pvp:
        t, v = min(com_pvp, key=lambda x: x[1])
        partes.append(f"Menor P/VP: <strong>{t}</strong> ({_fmt_num(v)}).")
    baratos = [t for t, v in com_pvp if v is not None and v < 1.0]
    if baratos:
        partes.append(f"{len(baratos)} FII(s) negociando abaixo do valor patrimonial "
                      f"(P/VP &lt; 1): {', '.join(baratos)}.")
    texto = " ".join(partes)
    return (f"<table role='presentation' width='100%' cellpadding='0' cellspacing='0' "
            f"style='background:#EEF4FB;border:1px solid #CFE0F0;border-radius:10px;"
            f"margin:8px 0 4px 0;'><tr><td style='padding:14px 18px;'>"
            f"<div style='font-family:Arial,sans-serif;font-size:14px;font-weight:bold;"
            f"color:#1F4E78;margin-bottom:4px;'>📌 Resumo executivo</div>"
            f"<div style='font-family:Arial,sans-serif;font-size:13px;color:#333;"
            f"line-height:1.6;'>{texto}</div></td></tr></table>")


def _barras_verticais(serie, cor):
    """serie = [{'label','valor'}]. Retorna HTML de barras verticais."""
    valores = [s for s in serie if isinstance(s.get("valor"), (int, float)) and s["valor"] >= 0]
    if not valores:
        return ""
    vmax = max(s["valor"] for s in valores) or 1
    celulas = []
    for s in valores:
        h = max(4, round(s["valor"] / vmax * 80))
        rotulo = str(s.get("label", ""))  # já vem como 'jan', 'fev', etc.
        celulas.append(
            f"<td valign='bottom' align='center' style='padding:0 2px;'>"
            f"<div style='font-size:8px;color:#888;margin-bottom:2px;'>{_fmt_num(s['valor'],3)}</div>"
            f"<div style='height:{h}px;width:13px;background:{cor};"
            f"border-radius:2px 2px 0 0;margin:0 auto;'></div>"
            f"<div style='font-size:8px;color:#999;margin-top:3px;'>{rotulo}</div>"
            f"</td>"
        )
    return (
        "<table role='presentation' cellpadding='0' cellspacing='0' "
        "style='margin:6px auto 0 auto;'><tr>" + "".join(celulas) + "</tr></table>"
    )


def _barras_horizontais(serie, cor):
    """serie = [{'nome'/'faixa', 'pct'(0-1)}]. Retorna HTML de barras horizontais."""
    itens = [s for s in serie if isinstance(s.get("pct"), (int, float))]
    if not itens:
        return ""
    linhas = []
    for s in itens:
        nome = s.get("nome") or s.get("faixa") or s.get("regiao") or "—"
        pct = max(0, min(1, float(s["pct"])))
        largura = round(pct * 100)
        linhas.append(
            "<tr>"
            f"<td style='font-size:12px;color:#444;padding:3px 8px 3px 0;"
            f"white-space:nowrap;'>{nome}</td>"
            f"<td style='padding:3px 0;width:100%;'>"
            f"<div style='background:#EDF1F6;border-radius:4px;width:100%;'>"
            f"<div style='width:{largura}%;background:{cor};height:13px;"
            f"border-radius:4px;'></div></div></td>"
            f"<td style='font-size:12px;color:#666;padding:3px 0 3px 8px;"
            f"white-space:nowrap;' align='right'>{_fmt_pct(pct)}</td>"
            "</tr>"
        )
    return (
        "<table role='presentation' cellpadding='0' cellspacing='0' width='100%' "
        "style='margin:4px 0;'>" + "".join(linhas) + "</table>"
    )


def _secao(titulo, conteudo_html):
    if not conteudo_html:
        return ""
    return (
        f"<div style='margin:14px 0 6px 0;'>"
        f"<div style='font-size:12px;font-weight:bold;color:{COR_PRIMARIA};"
        f"text-transform:uppercase;letter-spacing:0.5px;margin-bottom:2px;'>{titulo}</div>"
        f"{conteudo_html}</div>"
    )


def _chip(label, valor, cor_fundo, cor_texto):
    return (
        f"<td style='padding:8px 12px;background:{cor_fundo};border-radius:8px;'>"
        f"<div style='font-size:10px;color:{cor_texto};opacity:0.8;'>{label}</div>"
        f"<div style='font-size:16px;font-weight:bold;color:{cor_texto};'>{valor}</div>"
        f"</td>"
    )


def _lista_texto(texto, cor_marcador):
    if not texto:
        return ""
    partes = [p.strip() for p in str(texto).replace("\n", ";").split(";") if p.strip()]
    linhas = []
    for p in partes:
        linhas.append(
            f"<tr><td style='vertical-align:top;padding:2px 8px 2px 0;color:{cor_marcador};"
            f"font-weight:bold;'>•</td>"
            f"<td style='padding:2px 0;color:#444;font-size:13px;line-height:1.45;'>{p}</td></tr>"
        )
    return ("<table role='presentation' cellpadding='0' cellspacing='0'>"
            + "".join(linhas) + "</table>")


MESES_ABREV = ["jan", "fev", "mar", "abr", "mai", "jun",
               "jul", "ago", "set", "out", "nov", "dez"]


def _parse_mes(s):
    """Converte 'AAAA-MM' (ou MM/AAAA) em (chave_ordenavel, rotulo 'mmm').
    Em caso de falha retorna (0, texto curto)."""
    import re
    s = str(s).strip()
    m = re.search(r"(\d{4})[-/.](\d{1,2})", s)        # AAAA-MM
    if m:
        ano, mes = int(m.group(1)), int(m.group(2))
        if 1 <= mes <= 12:
            return (ano * 100 + mes, MESES_ABREV[mes - 1])
    m = re.search(r"(\d{1,2})[-/.](\d{2,4})", s)        # MM/AAAA
    if m:
        mes, ano = int(m.group(1)), int(m.group(2))
        if ano < 100:
            ano += 2000
        if 1 <= mes <= 12:
            return (ano * 100 + mes, MESES_ABREV[mes - 1])
    return (0, s[-3:])


def _grafico_rentabilidade(rent, cdi, ifix=None):
    """Barras comparando retorno 12m: FII vs CDI vs IFIX. Mostra o que houver."""
    rent, cdi, ifix = _num(rent), _num(cdi), _num(ifix)
    itens = [("Este FII", rent, COR_DY), ("CDI", cdi, "#9AA7B5"), ("IFIX", ifix, COR_PRAZO)]
    itens = [(n, v, c) for n, v, c in itens if v is not None]
    if not itens:
        return ""
    vmax = max([abs(v) for _, v, _ in itens] + [0.0001])

    linhas = []
    for nome, val, cor in itens:
        largura = round(max(0, val) / vmax * 100)
        cor_val = COR_VAC if val < 0 else "#444"
        linhas.append(
            "<tr>"
            f"<td style='font-size:12px;color:#444;padding:3px 8px 3px 0;"
            f"white-space:nowrap;'>{nome}</td>"
            f"<td style='padding:3px 0;width:100%;'>"
            f"<div style='background:#EDF1F6;border-radius:4px;width:100%;'>"
            f"<div style='width:{largura}%;background:{cor};height:14px;"
            f"border-radius:4px;'></div></div></td>"
            f"<td style='font-size:12px;color:{cor_val};font-weight:bold;"
            f"padding:3px 0 3px 8px;white-space:nowrap;' align='right'>{_fmt_pct(val)}</td>"
            "</tr>"
        )
    tabela = ("<table role='presentation' cellpadding='0' cellspacing='0' width='100%' "
              "style='margin:4px 0;'>" + "".join(linhas) + "</table>")
    return tabela + _veredito_rent(rent, cdi, ifix)


def _veredito_rent(rent, cdi, ifix):
    """Texto comparando o FII com CDI e IFIX."""
    rent, cdi, ifix = _num(rent), _num(cdi), _num(ifix)
    if rent is None:
        return ""
    partes = []
    if cdi is not None:
        d = rent - cdi
        cor = COR_INDEX if d >= 0 else COR_VAC
        seta = "▲" if d >= 0 else "▼"
        partes.append(f"<span style='color:{cor};'>{seta} {_fmt_pct(abs(d))} "
                      f"{'acima' if d >= 0 else 'abaixo'} do CDI</span>")
    if ifix is not None:
        d = rent - ifix
        cor = COR_INDEX if d >= 0 else COR_VAC
        seta = "▲" if d >= 0 else "▼"
        partes.append(f"<span style='color:{cor};'>{seta} {_fmt_pct(abs(d))} "
                      f"{'acima' if d >= 0 else 'abaixo'} do IFIX</span>")
    if not partes:
        return ""
    return (f"<div style='font-size:12px;margin-top:3px;font-weight:bold;'>"
            + " · ".join(partes) + "</div>")


def _gerar_linha_png(serie):
    """Gera gráfico de LINHA (FII vs CDI vs IFIX) em PNG. Retorna bytes ou None.
    serie = lista de {'mes','fii','cdi','ifix'} (retorno acumulado decimal).
    Desenha apenas as linhas que tiverem dados."""
    pontos = []
    for p in serie:
        if not isinstance(p, dict):
            continue
        fii = _num(p.get("fii"))
        cdi = _num(p.get("cdi"))
        ifix = _num(p.get("ifix"))
        if fii is None and cdi is None and ifix is None:
            continue
        chave, rotulo = _parse_mes(p.get("mes", ""))
        pontos.append((chave, rotulo, fii, cdi, ifix))
    if len(pontos) < 3:
        return None
    pontos.sort(key=lambda x: x[0])

    rotulos = [p[1] for p in pontos]
    series_def = [
        ("Este FII", "#2E75B6", [p[2] for p in pontos]),
        ("CDI", "#9AA7B5", [p[3] for p in pontos]),
        ("IFIX", "#C77B30", [p[4] for p in pontos]),
    ]

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from io import BytesIO

        fig, ax = plt.subplots(figsize=(6.0, 2.6), dpi=100)
        x = list(range(len(rotulos)))
        algum = False
        for nome, cor, vals in series_def:
            # só desenha a linha se tiver pelo menos um valor
            if any(v is not None for v in vals):
                vals_pct = [(v * 100 if v is not None else None) for v in vals]
                ax.plot(x, vals_pct, color=cor, marker="o", markersize=3,
                        linewidth=2, label=nome)
                algum = True
        if not algum:
            plt.close(fig)
            return None
        ax.set_xticks(x)
        ax.set_xticklabels(rotulos, fontsize=8)
        ax.tick_params(axis="y", labelsize=8)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0f}%"))
        ax.legend(fontsize=8, loc="upper left", frameon=False)
        ax.grid(True, axis="y", linestyle=":", alpha=0.5)
        for spine in ["top", "right"]:
            ax.spines[spine].set_visible(False)
        fig.tight_layout(pad=0.5)

        buf = BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight")
        plt.close(fig)
        return buf.getvalue()
    except Exception as e:
        print(f"  (aviso: falha ao gerar gráfico de linha: {e})")
        return None


# ----------------------------------------------------------------------
# Card de um FII
# ----------------------------------------------------------------------
def _card_fii(ticker, dados, imagens=None):
    tipo = (dados.get("tipo") or "").lower()
    tipo_label = {"papel": "Papel/CRI", "tijolo": "Tijolo",
                  "hibrido": "Híbrido", "fof": "FoF"}.get(tipo, "—")

    # Cota atual em destaque no cabeçalho (com o tipo abaixo, em letra menor)
    cota = _num(dados.get("cota_atual"))
    if cota is not None:
        cota_header = (
            f"<div style='color:#fff;font-size:17px;font-weight:bold;'>"
            f"R$ {_fmt_num(cota)}</div>"
            f"<div style='color:#AFC6E0;font-size:11px;'>{tipo_label}</div>"
        )
    else:
        cota_header = (f"<span style='background:rgba(255,255,255,0.18);color:#fff;"
                       f"font-size:11px;padding:3px 10px;border-radius:10px;'>{tipo_label}</span>")

    # Chips de topo (Últ. dividendo, DY, P/VP, Vacância, Tipo)
    ult_div = _num(dados.get("ultimo_dividendo"))
    chips = ["<table role='presentation' cellpadding='0' cellspacing='0'><tr>"]
    if ult_div is not None:
        chips.append(_chip("Últ. dividendo", f"R$ {_fmt_num(ult_div, 2)}", "#E6F4EA", COR_INDEX))
        chips.append("<td style='width:8px;'></td>")
    chips.append(_chip("DY 12M", _fmt_pct(dados.get("dy_12m")), "#E8F0F9", COR_PRIMARIA))
    chips.append("<td style='width:8px;'></td>")
    chips.append(_chip("P/VP", _fmt_num(dados.get("pvp")), "#E8F0F9", COR_PRIMARIA))
    if _num(dados.get("vacancia_fisica")) is not None:
        chips.append("<td style='width:8px;'></td>")
        chips.append(_chip("Vacância", _fmt_pct(dados.get("vacancia_fisica")), "#FBEAE8", COR_VAC))
    chips.append("<td style='width:8px;'></td>")
    chips.append(_chip("Tipo", tipo_label, "#EEF1F5", "#555"))
    chips.append("</tr></table>")
    chips_html = "".join(chips)

    # Descrição breve do fundo (no topo do card)
    descricao = dados.get("descricao")
    descricao_html = ""
    if descricao and str(descricao).strip().lower() not in ("none", "null", ""):
        descricao_html = (
            f"<div style='margin:0 0 12px 0;color:#555;font-size:13px;"
            f"font-style:italic;line-height:1.5;'>{descricao}</div>"
        )

    # Receita de locação do último mês (linha destacada)
    receita = dados.get("receita_locacao_mes")
    receita_html = ""
    if receita and str(receita).strip().lower() not in ("none", "null", "n/a", "—"):
        receita_html = (
            f"<div style='margin-top:10px;padding:8px 12px;background:#F1F6FB;"
            f"border-radius:8px;font-size:13px;color:#444;'>"
            f"🏢 <strong style='color:{COR_PRIMARIA};'>Receita de locação (último mês):</strong> "
            f"{receita}</div>"
        )

    # Fatos relevantes recentes (caixa destacada)
    fatos = [f for f in (dados.get("fatos_relevantes") or [])
             if isinstance(f, dict) and f.get("descricao")]
    fatos_html = ""
    if fatos:
        linhas = []
        for f in fatos[:3]:
            data_str = str(f.get("data", "")).strip()
            prefixo = (f"<strong style='color:#8A6D00;'>{data_str}:</strong> "
                       if data_str and data_str.lower() not in ("none", "null") else "")
            linhas.append(
                f"<tr><td style='vertical-align:top;padding:2px 8px 2px 0;'>📌</td>"
                f"<td style='padding:2px 0;color:#5C4B00;font-size:13px;line-height:1.45;'>"
                f"{prefixo}{f['descricao']}</td></tr>"
            )
        fatos_html = (
            f"<div style='margin-top:12px;padding:10px 14px;background:#FFF8E1;"
            f"border:1px solid #F2E2A8;border-radius:8px;'>"
            f"<div style='font-size:12px;font-weight:bold;color:#8A6D00;"
            f"text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px;'>"
            f"Fatos relevantes recentes</div>"
            f"<table role='presentation' cellpadding='0' cellspacing='0'>"
            + "".join(linhas) + "</table></div>"
        )

    # Gráfico DY mensal (ordenado cronologicamente, com mês abreviado)
    dy_mensal = dados.get("dy_mensal") or []
    serie_raw = [d for d in dy_mensal
                 if isinstance(d, dict) and isinstance(d.get("valor"), (int, float))]
    serie_raw.sort(key=lambda d: _parse_mes(d.get("mes", ""))[0])
    serie_dy = [{"label": _parse_mes(d.get("mes", ""))[1], "valor": d.get("valor")}
                for d in serie_raw]
    grafico_dy = _secao("DY mês a mês (R$/cota, últimos 12m)", _barras_verticais(serie_dy, COR_DY))

    # Rentabilidade 12m vs CDI vs IFIX: barras de comparação (mostra o que houver).
    grafico_rent = _secao(
        "Rentabilidade 12m (cota + dividendos) vs CDI vs IFIX",
        _grafico_rentabilidade(dados.get("rentabilidade_12m"),
                               dados.get("cdi_12m"),
                               dados.get("ifix_12m")))

    # Distribuição geográfica
    grafico_geo = _secao("Distribuição geográfica",
                         _barras_horizontais(dados.get("distribuicao_geografica") or [], "#3A7CA5"))

    # Principais inquilinos (com nota de concentração)
    inquilinos = [i for i in (dados.get("inquilinos") or [])
                  if isinstance(i, dict) and isinstance(i.get("pct"), (int, float))]
    grafico_inq = ""
    if inquilinos:
        barras_inq = _barras_horizontais(inquilinos, "#6A4C93")
        # Nota automática de concentração (top 3)
        top3 = sum(min(1, max(0, float(i["pct"]))) for i in inquilinos[:3])
        if top3 >= 0.6:
            nivel, cor_nota = "alta concentração", COR_VAC
        elif top3 >= 0.4:
            nivel, cor_nota = "concentração moderada", COR_PRAZO
        else:
            nivel, cor_nota = "bem diversificado", COR_INDEX
        nota = (
            f"<div style='font-size:11px;color:{cor_nota};margin-top:4px;'>"
            f"Top 3 inquilinos ≈ {_fmt_pct(top3)} da receita ({nivel})</div>"
        )
        grafico_inq = _secao("Principais inquilinos (% da receita)", barras_inq + nota)

    # Indexadores
    grafico_index = _secao("Indexadores dos contratos",
                           _barras_horizontais(dados.get("indexadores") or [], COR_INDEX))

    # Prazo dos contratos
    grafico_prazo = _secao("Prazo dos contratos (vencimento)",
                           _barras_horizontais(dados.get("prazo_contratos") or [], COR_PRAZO))

    # Positivos / Riscos
    positivos = _secao("Pontos positivos", _lista_texto(dados.get("positivos"), COR_INDEX))
    riscos = _secao("Riscos / Atenção", _lista_texto(dados.get("riscos"), COR_VAC))

    # Sugestão
    sug = (dados.get("sugestao") or "").strip()
    cores_sug = {"Comprar": "#1E7B46", "Manter": "#2E75B6",
                 "Aguardar": "#C77B30", "Vender": "#C0392B"}
    cor_sug = cores_sug.get(sug, "#555")
    sug_html = (
        f"<div style='margin-top:12px;'>"
        f"<span style='background:{cor_sug};color:#fff;font-size:12px;font-weight:bold;"
        f"padding:5px 14px;border-radius:14px;'>Sugestão da IA: {sug or '—'}</span></div>"
        if sug else ""
    )

    return f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
           style="margin:0 0 18px 0;border:1px solid #E3E8EF;border-radius:10px;
                  overflow:hidden;background:#ffffff;">
      <tr><td style="background:{COR_PRIMARIA};padding:13px 18px;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
          <td style="color:#fff;font-family:Arial,sans-serif;font-size:18px;
                     font-weight:bold;letter-spacing:0.5px;">{ticker}</td>
          <td align="right">{cota_header}</td>
        </tr></table>
      </td></tr>
      <tr><td style="padding:16px 18px;font-family:Arial,sans-serif;">
        {descricao_html}
        {chips_html}
        {receita_html}
        {fatos_html}
        {grafico_dy}
        {grafico_rent}
        {grafico_geo}
        {grafico_inq}
        {grafico_index}
        {grafico_prazo}
        {positivos}
        {riscos}
        {sug_html}
      </td></tr>
    </table>
    """


def _card_erro(ticker, erro):
    return f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
           style="margin:0 0 18px 0;border:1px solid #F3D6D2;border-radius:10px;
                  overflow:hidden;background:#fff;">
      <tr><td style="background:{COR_VAC};padding:13px 18px;color:#fff;
                 font-family:Arial,sans-serif;font-size:18px;font-weight:bold;">{ticker}</td></tr>
      <tr><td style="padding:14px 18px;font-family:Arial,sans-serif;">
        <p style="margin:0;color:{COR_VAC};font-size:13px;">⚠️ {erro}</p>
        <p style="margin:6px 0 0 0;color:#888;font-size:12px;">
          Consulte manualmente no Status Invest ou Funds Explorer.</p>
      </td></tr>
    </table>
    """


# ----------------------------------------------------------------------
# Montagem do e-mail
# ----------------------------------------------------------------------
def montar_html(resultados, cfg=None):
    # aceita dict {ticker: {...}} (do robo.py) ou lista [{...}]
    if isinstance(resultados, dict):
        resultados = list(resultados.values())
    hoje = datetime.now().strftime("%d/%m/%Y")
    meses_pt = ["janeiro", "fevereiro", "março", "abril", "maio", "junho",
                "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
    mes_ref = f"{meses_pt[datetime.now().month - 1]} de {datetime.now().year}"
    sucesso = sum(1 for r in resultados if "dados" in r)
    falha = len(resultados) - sucesso

    imagens = []  # (cid, png_bytes) para anexar inline
    cards = []
    dados_resumo = []
    for r in resultados:
        if "dados" in r:
            d = r["dados"]
            d["_ticker"] = r["ticker"]
            dados_resumo.append(d)
            cards.append(_card_fii(r["ticker"], d, imagens))
        else:
            cards.append(_card_erro(r["ticker"], r.get("erro", "erro desconhecido")))
    bloco_resumo = _resumo_executivo(dados_resumo)

    falha_chip = (f"<td style='width:10px;'></td>"
                  f"<td style='padding:6px 14px;background:#FBEAE8;border-radius:8px;"
                  f"font-family:Arial,sans-serif;font-size:13px;color:#C0392B;"
                  f"font-weight:bold;'>⚠ {falha} com erro</td>") if falha else ""


    html = f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#EEF1F5;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#EEF1F5;">
    <tr><td align="center" style="padding:24px 12px;">
      <table role="presentation" width="640" cellpadding="0" cellspacing="0"
             style="max-width:640px;width:100%;background:#fff;border-radius:12px;
                    overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,0.08);">
        <tr><td style="background:{COR_PRIMARIA};padding:28px;">
          <div style="font-family:Arial,sans-serif;color:#fff;font-size:22px;font-weight:bold;">
            📊 Análise da Carteira de FIIs</div>
          <div style="font-family:Arial,sans-serif;color:#AFC6E0;font-size:14px;margin-top:4px;">
            Relatório de {mes_ref}</div>
        </td></tr>
        <tr><td style="padding:18px 28px 4px 28px;">
          <table role="presentation" cellpadding="0" cellspacing="0"><tr>
            <td style="padding:6px 14px;background:#E8F3EC;border-radius:8px;
                       font-family:Arial,sans-serif;font-size:13px;color:#1E7B46;
                       font-weight:bold;">✓ {sucesso} analisados</td>
            {falha_chip}
          </tr></table>
        </td></tr>
        <tr><td style="padding:14px 28px 8px 28px;">{bloco_resumo}{''.join(cards)}</td></tr>
        <tr><td style="padding:8px 28px 28px 28px;">
          <div style="border-top:1px solid #E3E8EF;padding-top:16px;
                      font-family:Arial,sans-serif;font-size:12px;color:#94A3B8;line-height:1.6;">
            Gerado em {hoje} · Fonte: Google Gemini com busca na web.<br>
            ⚠️ Os números e gráficos são <strong>estimados pela IA</strong> e podem conter
            imprecisões. Confira sempre nos relatórios oficiais antes de decidir.
            <strong>Não é recomendação de investimento.</strong>
          </div>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""
    return html, imagens


# ----------------------------------------------------------------------
# Envio de e-mail
# ----------------------------------------------------------------------
