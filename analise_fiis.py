#!/usr/bin/env python3
"""
Análise mensal de FIIs via Gemini (com grounding/busca) + e-mail visual com gráficos.

Sem scraping: o próprio Gemini pesquisa na web os dados de cada FII e retorna
dados estruturados (JSON), que viram gráficos de barras em HTML/CSS no e-mail.

Variáveis de ambiente (Secrets no GitHub):
  GEMINI_API_KEY, GMAIL_USER, GMAIL_APP_PASSWORD
  EMAIL_TO (opcional), FIIS (opcional, separado por vírgula)
"""

import os
import sys
import time
import json
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import requests

# ----------------------------------------------------------------------
# Configuração
# ----------------------------------------------------------------------
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GMAIL_USER = os.environ.get("GMAIL_USER", "").strip()
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "").strip()

ARQUIVO_SETTINGS = "settings.txt"


def carregar_settings():
    """Lê settings.txt (formato CHAVE=valor). Linhas com # são comentário."""
    settings = {}
    caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), ARQUIVO_SETTINGS)
    if os.path.exists(caminho):
        with open(caminho, "r", encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if not linha or linha.startswith("#") or "=" not in linha:
                    continue
                chave, _, valor = linha.partition("=")
                settings[chave.strip().upper()] = valor.split("#")[0].strip()
    return settings


SETTINGS = carregar_settings()

# Destinatário: env > settings.txt > o próprio Gmail
EMAIL_TO = (os.environ.get("EMAIL_TO", "").strip()
            or SETTINGS.get("EMAIL_TO", "").strip()
            or GMAIL_USER)

# Dia do mês para o envio agendado (usado junto com a verificação no main)
try:
    DIA_DO_MES = int(SETTINGS.get("DIA_DO_MES", "20"))
except ValueError:
    DIA_DO_MES = 20

MODEL = SETTINGS.get("MODEL", "").strip() or "gemini-2.5-flash-lite"
API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{MODEL}:generateContent"
)

DEFAULT_FIIS = [
    "MXRF11", "KNCR11", "KNSC11", "RBRR11", "MCCI11",
    "HGLG11", "BRCO11", "BTLG11", "XPLG11",
    "HGBS11", "XPML11", "HSML11",
    "TRXF11", "HGRU11", "KNRI11", "RBRX11",
]

ARQUIVO_CARTEIRA = "carteira.txt"


def carregar_fiis():
    """Determina a lista de FIIs, na ordem de prioridade:
    1) variável de ambiente FIIS (separada por vírgula)
    2) arquivo carteira.txt (um ticker por linha; # = comentário)
    3) lista padrão embutida (DEFAULT_FIIS)
    """
    # 1) Variável de ambiente
    env_fiis = os.environ.get("FIIS", "").strip()
    if env_fiis:
        tickers = [t.strip().upper() for t in env_fiis.split(",") if t.strip()]
        if tickers:
            print(f"Carteira: usando variável de ambiente FIIS ({len(tickers)} FIIs)")
            return tickers

    # 2) Arquivo carteira.txt (procura ao lado do script)
    caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), ARQUIVO_CARTEIRA)
    if os.path.exists(caminho):
        tickers = []
        with open(caminho, "r", encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if not linha or linha.startswith("#"):
                    continue
                # aceita "MXRF11" ou "MXRF11  # comentário"
                ticker = linha.split("#")[0].strip().upper()
                if ticker:
                    tickers.append(ticker)
        if tickers:
            print(f"Carteira: lida de {ARQUIVO_CARTEIRA} ({len(tickers)} FIIs)")
            return tickers
        print(f"Aviso: {ARQUIVO_CARTEIRA} está vazio; usando lista padrão.")

    # 3) Lista padrão
    print(f"Carteira: usando lista padrão embutida ({len(DEFAULT_FIIS)} FIIs)")
    return DEFAULT_FIIS


FIIS = carregar_fiis()

try:
    PAUSA_ENTRE_FIIS = int(SETTINGS.get("PAUSA_SEGUNDOS", "20"))
except ValueError:
    PAUSA_ENTRE_FIIS = 20
ESPERA_RODADA = 120        # 2 min de espera antes de re-tentar os que deram 429
MAX_RODADAS = 6            # máximo de rodadas de retry (evita loop infinito)

# Paleta
COR_PRIMARIA = "#1F4E78"
COR_DY = "#2E75B6"
COR_INDEX = "#1E7B46"
COR_PRAZO = "#C77B30"
COR_VAC = "#C0392B"


# ----------------------------------------------------------------------
# Chamada ao Gemini — retorna dados estruturados (JSON)
# ----------------------------------------------------------------------
def analisar_fii(ticker: str) -> dict:
    prompt = (
        f"Pesquise dados públicos ATUAIS do fundo imobiliário brasileiro {ticker} "
        f"(relatório gerencial mais recente, Status Invest, Funds Explorer, Fundamentus).\n\n"
        f"Responda APENAS com um objeto JSON válido (sem markdown, sem texto extra), "
        f"com estes campos. Use null quando NÃO tiver certeza — NÃO invente números:\n"
        f"{{\n"
        f'  "descricao": "<descrição breve do fundo em 1 frase: o que é, segmento, gestora>",\n'
        f'  "tipo": "papel|tijolo|hibrido|fof",\n'
        f'  "dy_12m": <decimal ex 0.115 ou null>,\n'
        f'  "pvp": <decimal ex 0.92 ou null>,\n'
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
        f"}}"
    )

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 4000,
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    headers = {"Content-Type": "application/json"}
    params = {"key": GEMINI_API_KEY}

    try:
        resp = requests.post(API_URL, headers=headers, params=params,
                             data=json.dumps(payload), timeout=120)
    except Exception as e:
        return {"ticker": ticker, "erro": f"Falha de conexão: {e}"}

    if resp.status_code == 429:
        # Sinaliza rate limit para o main tentar de novo numa próxima rodada
        return {"ticker": ticker, "erro": "Rate limit (429)", "rate_limited": True}

    if resp.status_code != 200:
        return {"ticker": ticker, "erro": f"HTTP {resp.status_code}: {resp.text[:160]}"}

    try:
        data = resp.json()
        cand = data["candidates"][0]
        if cand.get("finishReason") == "MAX_TOKENS":
            return {"ticker": ticker, "erro": "Resposta truncada (MAX_TOKENS)"}
        texto = cand["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        return {"ticker": ticker, "erro": f"Resposta inesperada: {e}"}

    dados = _extrair_json(texto)
    if dados is None:
        return {"ticker": ticker, "erro": "JSON inválido da IA"}
    return {"ticker": ticker, "dados": dados}


def _extrair_json(texto: str):
    i = texto.find("{")
    j = texto.rfind("}")
    if i == -1 or j == -1 or j < i:
        return None
    try:
        return json.loads(texto[i:j + 1])
    except Exception:
        return None


# ----------------------------------------------------------------------
# Helpers de formatação
# ----------------------------------------------------------------------
def _fmt_pct(v):
    try:
        return f"{float(v) * 100:.1f}%".replace(".", ",")
    except (TypeError, ValueError):
        return "—"

def _fmt_num(v, casas=2):
    try:
        return f"{float(v):.{casas}f}".replace(".", ",")
    except (TypeError, ValueError):
        return "—"

def _fmt_money(v):
    try:
        return f"R$ {float(v):.4f}".replace(".", ",")
    except (TypeError, ValueError):
        return "—"


def _barras_verticais(serie, cor):
    """serie = [{'label','valor'}]. Retorna HTML de barras verticais."""
    valores = [s for s in serie if isinstance(s.get("valor"), (int, float)) and s["valor"] >= 0]
    if not valores:
        return ""
    vmax = max(s["valor"] for s in valores) or 1
    celulas = []
    for s in valores:
        h = max(4, round(s["valor"] / vmax * 80))
        rotulo = str(s.get("label", ""))[-2:]  # mostra só o mês (MM)
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


# ----------------------------------------------------------------------
# Card de um FII
# ----------------------------------------------------------------------
def _card_fii(ticker, dados):
    tipo = (dados.get("tipo") or "").lower()
    tipo_label = {"papel": "Papel/CRI", "tijolo": "Tijolo",
                  "hibrido": "Híbrido", "fof": "FoF"}.get(tipo, "—")

    # Chips de topo (DY, P/VP, Vacância, Tipo)
    chips = ["<table role='presentation' cellpadding='0' cellspacing='0'><tr>"]
    chips.append(_chip("DY 12M", _fmt_pct(dados.get("dy_12m")), "#E8F0F9", COR_PRIMARIA))
    chips.append("<td style='width:8px;'></td>")
    chips.append(_chip("P/VP", _fmt_num(dados.get("pvp")), "#E8F0F9", COR_PRIMARIA))
    if isinstance(dados.get("vacancia_fisica"), (int, float)):
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

    # Gráfico DY mensal
    dy_mensal = dados.get("dy_mensal") or []
    serie_dy = [{"label": d.get("mes", ""), "valor": d.get("valor")}
                for d in dy_mensal if isinstance(d, dict)]
    grafico_dy = _secao("DY mês a mês (R$/cota, últimos 12m)", _barras_verticais(serie_dy, COR_DY))

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
          <td align="right"><span style="background:rgba(255,255,255,0.18);color:#fff;
                     font-size:11px;padding:3px 10px;border-radius:10px;">{tipo_label}</span></td>
        </tr></table>
      </td></tr>
      <tr><td style="padding:16px 18px;font-family:Arial,sans-serif;">
        {descricao_html}
        {chips_html}
        {receita_html}
        {fatos_html}
        {grafico_dy}
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
def montar_html(resultados: list) -> str:
    hoje = datetime.now().strftime("%d/%m/%Y")
    meses_pt = ["janeiro", "fevereiro", "março", "abril", "maio", "junho",
                "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
    mes_ref = f"{meses_pt[datetime.now().month - 1]} de {datetime.now().year}"
    sucesso = sum(1 for r in resultados if "dados" in r)
    falha = len(resultados) - sucesso

    cards = []
    for r in resultados:
        if "dados" in r:
            cards.append(_card_fii(r["ticker"], r["dados"]))
        else:
            cards.append(_card_erro(r["ticker"], r.get("erro", "erro desconhecido")))

    falha_chip = (f"<td style='width:10px;'></td>"
                  f"<td style='padding:6px 14px;background:#FBEAE8;border-radius:8px;"
                  f"font-family:Arial,sans-serif;font-size:13px;color:#C0392B;"
                  f"font-weight:bold;'>⚠ {falha} com erro</td>") if falha else ""

    return f"""<!DOCTYPE html>
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
        <tr><td style="padding:14px 28px 8px 28px;">{''.join(cards)}</td></tr>
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


# ----------------------------------------------------------------------
# Envio de e-mail
# ----------------------------------------------------------------------
def enviar_email(html: str):
    msg = MIMEMultipart("alternative")
    meses_pt = ["janeiro", "fevereiro", "março", "abril", "maio", "junho",
                "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
    msg["Subject"] = f"📊 Análise dos FIIs — {meses_pt[datetime.now().month-1]}/{datetime.now().year}"
    msg["From"] = GMAIL_USER
    msg["To"] = EMAIL_TO
    msg.attach(MIMEText(html, "html", "utf-8"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_USER, EMAIL_TO.split(","), msg.as_string())


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main():
    faltando = [v for v in ["GEMINI_API_KEY", "GMAIL_USER", "GMAIL_APP_PASSWORD"]
                if not os.environ.get(v, "").strip()]
    if faltando:
        print(f"ERRO: variáveis de ambiente faltando: {', '.join(faltando)}")
        sys.exit(1)

    # Verificação do dia: quando acionado pelo AGENDADOR (schedule), só roda no
    # dia configurado em settings.txt (DIA_DO_MES). Acionamento manual
    # (workflow_dispatch) ou execução local rodam sempre.
    evento = os.environ.get("GITHUB_EVENT_NAME", "").strip()
    if evento == "schedule":
        hoje = datetime.now().day
        if hoje != DIA_DO_MES:
            print(f"Agendado para o dia {DIA_DO_MES}; hoje é dia {hoje}. "
                  f"Encerrando sem executar.")
            sys.exit(0)
        print(f"Dia {hoje} = dia configurado ({DIA_DO_MES}). Executando análise.")

    print(f"Analisando {len(FIIS)} FIIs: {', '.join(FIIS)}")

    # resultados: ticker -> dict (guarda o que já foi obtido)
    resultados = {}
    pendentes = list(FIIS)  # FIIs ainda sem dados (ou que deram 429)

    for rodada in range(1, MAX_RODADAS + 1):
        if not pendentes:
            break
        if rodada > 1:
            print(f"\n--- Rodada {rodada}: re-tentando {len(pendentes)} FII(s) "
                  f"que deram rate limit ---")

        ainda_429 = []
        for i, ticker in enumerate(pendentes, 1):
            print(f"[rodada {rodada}] [{i}/{len(pendentes)}] {ticker}...")
            r = analisar_fii(ticker)

            if "dados" in r:
                resultados[ticker] = r
                print("  -> OK")
            elif r.get("rate_limited"):
                # Guarda o erro (caso seja a última rodada) e marca para re-tentar
                resultados[ticker] = r
                ainda_429.append(ticker)
                print("  -> 429 (será re-tentado)")
            else:
                resultados[ticker] = r
                print(f"  -> ERRO: {r['erro']}")

            time.sleep(PAUSA_ENTRE_FIIS)

        pendentes = ainda_429
        if pendentes and rodada < MAX_RODADAS:
            print(f"\nAguardando {ESPERA_RODADA}s para a cota renovar antes da "
                  f"próxima rodada ({len(pendentes)} pendente(s))...")
            time.sleep(ESPERA_RODADA)

    if pendentes:
        print(f"\nATENÇÃO: {len(pendentes)} FII(s) seguem com 429 após "
              f"{MAX_RODADAS} rodadas: {', '.join(pendentes)}. "
              f"Enviando e-mail com o que foi obtido.")

    # Reordena os resultados na ordem original da carteira
    resultados_ordenados = [resultados[t] for t in FIIS if t in resultados]

    print("\nMontando e enviando e-mail...")
    html = montar_html(resultados_ordenados)
    try:
        enviar_email(html)
        print(f"E-mail enviado para {EMAIL_TO}")
    except Exception as e:
        print(f"ERRO ao enviar e-mail: {e}")
        with open("analise_falhou.html", "w", encoding="utf-8") as f:
            f.write(html)
        sys.exit(1)


if __name__ == "__main__":
    main()
