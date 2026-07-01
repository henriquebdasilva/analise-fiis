"""Radar de oportunidades + comparação com a média do setor (#5)."""
from datetime import datetime

from core.util import _num, _fmt_pct, _fmt_num

COR_PRIMARIA = "#1F4E78"
COR_VERDE = "#1E7B46"


def montar_prompt(ticker):
    return (
        f"Pesquise dados públicos ATUAIS do fundo imobiliário brasileiro {ticker} "
        f"(Status Invest, Funds Explorer, Fundamentus).\n\n"
        f"Avalie se é uma OPORTUNIDADE DE COMPRA hoje. Responda APENAS JSON válido "
        f"(sem markdown). Use null quando não tiver certeza — NÃO invente números:\n"
        f"{{\n"
        f'  "cota_atual": <preço atual da cota em reais, decimal, ou null>,\n'
        f'  "pvp": <P/VP atual, decimal ex 0.92, ou null>,\n'
        f'  "dy_12m": <dividend yield 12m, decimal ex 0.115, ou null>,\n'
        f'  "minima_52s": <menor cotação das últimas 52 semanas, decimal, ou null>,\n'
        f'  "maxima_52s": <maior cotação das últimas 52 semanas, decimal, ou null>,\n'
        f'  "pvp_medio_setor": <P/VP médio do segmento deste fundo (papel, logística, '
        f'shopping, etc.) hoje, decimal, ou null se não souber>,\n'
        f'  "segmento": "<segmento do fundo em uma palavra: papel/logística/shopping/'
        f'híbrido/renda urbana/lajes/FoF/outros>",\n'
        f'  "nota": "<Atrativo|Neutro|Caro — Atrativo se P/VP<=1 E cota perto da mínima '
        f'de 52s E DY consistente; Caro se P/VP alto ou cota perto da máxima>",\n'
        f'  "motivo": "<1-2 frases objetivas citando P/VP, posição vs mínima de 52 semanas '
        f'e DY, e o principal risco. Seja equilibrado.>",\n'
        f'  "composicao": [<até 5 itens {{"item":"<ativo/segmento>","pct":<0-1 ou null>}}, '
        f'do maior ao menor; [] se não encontrar>],\n'
        f'  "vantagens": "<2 a 3 vantagens competitivas concretas, separadas por ;>",\n'
        f'  "tese": "<tese de investimento em 2-3 frases, considerando o cenário macro>"\n'
        f"}}"
    )


def filtrar_atrativos(resultados, fiis):
    atrativos = []
    for t in fiis:
        r = resultados.get(t)
        if r and "dados" in r:
            nota = (r["dados"].get("nota") or "").strip().lower()
            if "atrativo" in nota:
                atrativos.append(r)
    return atrativos


def _barras_composicao(itens):
    if not itens:
        return ""
    linhas = []
    for it in itens[:5]:
        if not isinstance(it, dict):
            continue
        nome = (it.get("item") or "").strip()
        if not nome:
            continue
        pct = _num(it.get("pct"))
        if pct is not None:
            largura = max(3, min(100, round(pct * 100)))
            barra = (f"<div style='background:#E3E8EF;border-radius:4px;height:14px;"
                     f"width:100%;margin-top:2px;'><div style='background:{COR_PRIMARIA};"
                     f"height:14px;border-radius:4px;width:{largura}%;'></div></div>")
            linhas.append(
                f"<div style='margin:5px 0;'>"
                f"<table role='presentation' width='100%' cellpadding='0' cellspacing='0'><tr>"
                f"<td style='font-family:Arial,sans-serif;font-size:12px;color:#333;'>{nome}</td>"
                f"<td align='right' style='font-family:Arial,sans-serif;font-size:12px;"
                f"color:#5A6B7B;font-weight:bold;'>{_fmt_pct(pct)}</td></tr></table>{barra}</div>")
        else:
            linhas.append(f"<div style='font-family:Arial,sans-serif;font-size:12px;"
                          f"color:#333;margin:4px 0;'>• {nome}</div>")
    if not linhas:
        return ""
    return (f"<div style='margin-top:10px;'><div style='font-family:Arial,sans-serif;"
            f"font-size:12px;font-weight:bold;color:{COR_PRIMARIA};margin-bottom:2px;'>"
            f"📦 Composição</div>{''.join(linhas)}</div>")


def _bloco_texto(titulo, texto, separar=False):
    texto = (texto or "").strip()
    if not texto:
        return ""
    if separar:
        itens = [t.strip() for t in texto.split(";") if t.strip()]
        corpo = "".join(f"<div style='font-family:Arial,sans-serif;font-size:13px;"
                        f"color:#333;margin:3px 0;line-height:1.5;'>✓ {it}</div>" for it in itens)
    else:
        corpo = (f"<div style='font-family:Arial,sans-serif;font-size:13px;color:#333;"
                 f"line-height:1.5;'>{texto}</div>")
    return (f"<div style='margin-top:10px;'><div style='font-family:Arial,sans-serif;"
            f"font-size:12px;font-weight:bold;color:{COR_PRIMARIA};margin-bottom:2px;'>"
            f"{titulo}</div>{corpo}</div>")


def _comparacao_setor(pvp, pvp_setor, segmento):
    """#5 — compara o P/VP do fundo com a média do setor."""
    pvp = _num(pvp)
    pvp_setor = _num(pvp_setor)
    if pvp is None or pvp_setor is None or pvp_setor <= 0:
        return ""
    dif = (pvp - pvp_setor) / pvp_setor * 100
    seg = (segmento or "setor").strip()
    if dif <= -3:
        cor, txt = COR_VERDE, f"{_fmt_num(abs(dif))}% mais barato que a média de {seg}"
    elif dif >= 3:
        cor, txt = "#C0392B", f"{_fmt_num(abs(dif))}% mais caro que a média de {seg}"
    else:
        cor, txt = "#5A6B7B", f"em linha com a média de {seg}"
    return (f"<div style='margin-top:8px;font-family:Arial,sans-serif;font-size:12px;'>"
            f"<span style='color:#5A6B7B;'>Vs. setor (P/VP médio {_fmt_num(pvp_setor)}): </span>"
            f"<span style='color:{cor};font-weight:bold;'>{txt}</span></div>")


def _card(ticker, d):
    cota = _num(d.get("cota_atual"))
    pvp = _num(d.get("pvp"))
    dy = _num(d.get("dy_12m"))
    minima = _num(d.get("minima_52s"))
    motivo = (d.get("motivo") or "").strip()

    chips = []
    if pvp is not None:
        chips.append(f"P/VP {_fmt_num(pvp)}")
    if dy is not None:
        chips.append(f"DY {_fmt_pct(dy)}")
    if cota is not None and minima is not None and minima > 0:
        chips.append(f"{_fmt_pct((cota - minima) / minima)} acima da mín. 52s")
    chips_txt = " · ".join(chips)
    cota_txt = f"R$ {_fmt_num(cota)}" if cota is not None else ""

    comp_setor = _comparacao_setor(pvp, d.get("pvp_medio_setor"), d.get("segmento"))
    composicao = _barras_composicao(d.get("composicao"))
    vantagens = _bloco_texto("⭐ Vantagens", d.get("vantagens"), separar=True)
    tese = _bloco_texto("💡 Tese de investimento", d.get("tese"))

    return (
        f"<div style='padding:14px 0;border-bottom:1px solid #E3E8EF;'>"
        f"<table role='presentation' width='100%' cellpadding='0' cellspacing='0'><tr>"
        f"<td style='font-family:Arial,sans-serif;font-size:16px;font-weight:bold;"
        f"color:{COR_VERDE};'>🟢 {ticker}</td>"
        f"<td align='right' style='font-family:Arial,sans-serif;font-size:15px;"
        f"font-weight:bold;color:{COR_PRIMARIA};'>{cota_txt}</td></tr></table>"
        f"<div style='font-family:Arial,sans-serif;font-size:12px;color:#5A6B7B;"
        f"margin-top:3px;'>{chips_txt}</div>"
        f"<div style='font-family:Arial,sans-serif;font-size:13px;color:#333;"
        f"margin-top:5px;line-height:1.5;'>{motivo}</div>"
        f"{comp_setor}{composicao}{vantagens}{tese}</div>"
    )


def montar_html(atrativos, cfg=None):
    hoje = datetime.now().strftime("%d/%m/%Y")
    atrativos.sort(key=lambda x: (_num(x["dados"].get("pvp")) is None,
                                  _num(x["dados"].get("pvp")) or 999))
    cards = "".join(_card(a["ticker"], a["dados"]) for a in atrativos)
    return f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#EEF1F5;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#EEF1F5;">
    <tr><td align="center" style="padding:24px 12px;">
      <table role="presentation" width="600" cellpadding="0" cellspacing="0"
             style="max-width:600px;width:100%;background:#fff;border-radius:12px;
                    overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,0.08);">
        <tr><td style="background:{COR_VERDE};padding:24px 28px;">
          <div style="font-family:Arial,sans-serif;color:#fff;font-size:20px;font-weight:bold;">
            🎯 Radar de Oportunidades — FIIs</div>
          <div style="font-family:Arial,sans-serif;color:#C8E6D0;font-size:13px;margin-top:4px;">
            {hoje} · {len(atrativos)} oportunidade(s) hoje</div>
        </td></tr>
        <tr><td style="padding:18px 28px 8px 28px;">
          <div style="font-family:Arial,sans-serif;font-size:13px;color:#5A6B7B;margin-bottom:6px;">
            FIIs atrativos hoje, por P/VP, posição vs mínima de 52 semanas, DY e
            comparação com o setor. Ordenados por P/VP.</div>
          {cards}
        </td></tr>
        <tr><td style="padding:8px 28px 24px 28px;">
          <div style="border-top:1px solid #E3E8EF;padding-top:14px;
                      font-family:Arial,sans-serif;font-size:12px;color:#94A3B8;line-height:1.6;">
            Gerado em {hoje} · Fonte: Google Gemini com busca na web.<br>
            ⚠️ Números <strong>estimados pela IA</strong>, podem conter imprecisões.
            Confira no Status Invest antes de decidir.
            <strong>Não é recomendação de investimento.</strong>
          </div>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""
