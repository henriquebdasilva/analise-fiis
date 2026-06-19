#!/usr/bin/env python3
"""
Radar de Oportunidades de FIIs — serviço DIÁRIO e independente.

Roda separado do relatório mensal (analise_fiis.py). Uma vez por dia, pergunta
ao Gemini (com busca na web) quais FIIs da carteira estão atrativos para compra
hoje, olhando P/VP, mínima/máxima de 52 semanas e DY. Envia um e-mail curto só
com as oportunidades encontradas.

Compartilha os mesmos secrets/arquivos do outro serviço:
- GEMINI_API_KEY, GMAIL_USER, GMAIL_APP_PASSWORD, EMAIL_TO (env/secrets)
- carteira.txt (mesma lista de FIIs)
- settings.txt (lê MODEL, PAUSA_SEGUNDOS, EMAIL_TO)
"""
import os
import sys
import json
import time
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import requests

# ----------------------------------------------------------------------
# Configuração (espelha analise_fiis.py)
# ----------------------------------------------------------------------
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GMAIL_USER = os.environ.get("GMAIL_USER", "").strip()
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "").strip()

ARQUIVO_SETTINGS = "settings.txt"
ARQUIVO_CARTEIRA = "carteira.txt"

DEFAULT_FIIS = [
    "MXRF11", "KNCR11", "KNSC11", "RBRR11", "MCCI11",
    "HGLG11", "BRCO11", "BTLG11", "XPLG11",
    "HGBS11", "XPML11", "HSML11",
    "TRXF11", "HGRU11", "KNRI11", "RBRX11",
]


def carregar_settings():
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
EMAIL_TO = (os.environ.get("EMAIL_TO", "").strip()
            or SETTINGS.get("EMAIL_TO", "").strip()
            or GMAIL_USER)
MODEL = SETTINGS.get("MODEL", "").strip() or "gemini-2.5-flash-lite"
API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{MODEL}:generateContent"
)
try:
    PAUSA_ENTRE_FIIS = int(SETTINGS.get("PAUSA_SEGUNDOS", "20"))
except ValueError:
    PAUSA_ENTRE_FIIS = 20
ESPERA_RODADA = 120
MAX_RODADAS = 6

# Cores do e-mail
COR_PRIMARIA = "#1F4E78"
COR_VERDE = "#1E7B46"
COR_VAC = "#C0392B"


def carregar_fiis():
    env = os.environ.get("FIIS", "").strip()
    if env:
        return [t.strip().upper() for t in env.replace("\n", ",").split(",") if t.strip()]
    caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), ARQUIVO_CARTEIRA)
    if os.path.exists(caminho):
        fiis = []
        with open(caminho, "r", encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if linha and not linha.startswith("#"):
                    fiis.append(linha.upper())
        if fiis:
            print(f"Carteira: lida de {ARQUIVO_CARTEIRA} ({len(fiis)} FIIs)")
            return fiis
    print(f"Carteira: usando lista padrão embutida ({len(DEFAULT_FIIS)} FIIs)")
    return DEFAULT_FIIS


FIIS = carregar_fiis()


# ----------------------------------------------------------------------
# Helpers numéricos
# ----------------------------------------------------------------------
def _num(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.strip().replace("R$", "").replace("%", "").replace(" ", "")
        if not s:
            return None
        if "," in s and "." in s:
            s = s.replace(".", "").replace(",", ".")
        elif "," in s:
            s = s.replace(",", ".")
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _fmt_pct(v):
    v = _num(v)
    return "—" if v is None else f"{v * 100:.1f}%".replace(".", ",")


def _fmt_num(v, casas=2):
    v = _num(v)
    return "—" if v is None else f"{v:.{casas}f}".replace(".", ",")


def _extrair_json(texto):
    ini = texto.find("{")
    fim = texto.rfind("}")
    if ini == -1 or fim == -1:
        return None
    try:
        return json.loads(texto[ini:fim + 1])
    except json.JSONDecodeError:
        return None


# ----------------------------------------------------------------------
# Consulta ao Gemini
# ----------------------------------------------------------------------
def avaliar_fii(ticker):
    prompt = (
        f"Pesquise dados públicos ATUAIS do fundo imobiliário brasileiro {ticker} "
        f"(Status Invest, Funds Explorer, Fundamentus).\n\n"
        f"Avalie se é uma OPORTUNIDADE DE COMPRA hoje. Responda APENAS com JSON válido "
        f"(sem markdown). Use null quando não tiver certeza — NÃO invente números:\n"
        f"{{\n"
        f'  "cota_atual": <preço atual da cota em reais, decimal, ou null>,\n'
        f'  "pvp": <P/VP atual, decimal ex 0.92, ou null>,\n'
        f'  "dy_12m": <dividend yield dos últimos 12 meses, decimal ex 0.115, ou null>,\n'
        f'  "minima_52s": <menor cotação das últimas 52 semanas, decimal, ou null>,\n'
        f'  "maxima_52s": <maior cotação das últimas 52 semanas, decimal, ou null>,\n'
        f'  "nota": "<Atrativo|Neutro|Caro — Atrativo se P/VP<=1 E cota perto da mínima '
        f'de 52s E DY consistente; Caro se P/VP alto ou cota perto da máxima>",\n'
        f'  "motivo": "<1-2 frases objetivas citando P/VP, posição vs mínima de 52 semanas '
        f'e DY, e o principal risco. Seja equilibrado.>",\n'
        f'  "composicao": [<composição da carteira do fundo: principais ativos/segmentos e '
        f'seu peso, cada item {{"item":"<ex: CRIs indexados ao IPCA / Galpões logísticos SP / '
        f'Shoppings>","pct":<0-1 ou null se não souber o percentual>}}, máximo 5, do maior ao '
        f'menor; [] se não encontrar>],\n'
        f'  "vantagens": "<2 a 3 vantagens competitivas concretas deste fundo, separadas por '
        f'; (ex: gestão experiente, contratos longos atípicos, baixa vacância, boa liquidez)>",\n'
        f'  "tese": "<tese de investimento em 2-3 frases: por que faz sentido ter este FII na '
        f'carteira hoje, considerando o cenário macro (Selic/juros) e o posicionamento do '
        f'fundo. Seja específico e equilibrado.>"\n'
        f"}}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {"thinkingConfig": {"thinkingBudget": 0}, "maxOutputTokens": 3000},
    }
    headers = {"Content-Type": "application/json"}
    params = {"key": GEMINI_API_KEY}
    try:
        resp = requests.post(API_URL, headers=headers, params=params,
                             data=json.dumps(payload), timeout=120)
    except Exception as e:
        return {"ticker": ticker, "erro": f"Conexão: {e}"}

    if resp.status_code == 429:
        return {"ticker": ticker, "erro": "Rate limit (429)", "rate_limited": True}
    if resp.status_code != 200:
        return {"ticker": ticker, "erro": f"HTTP {resp.status_code}"}
    try:
        cand = resp.json()["candidates"][0]
        if cand.get("finishReason") == "MAX_TOKENS":
            return {"ticker": ticker, "erro": "Resposta truncada"}
        texto = cand["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        return {"ticker": ticker, "erro": f"Resposta inesperada: {e}"}

    dados = _extrair_json(texto)
    if dados is None:
        return {"ticker": ticker, "erro": "JSON inválido"}
    return {"ticker": ticker, "dados": dados}


# ----------------------------------------------------------------------
# E-mail
# ----------------------------------------------------------------------
def _barras_composicao(itens):
    """Mini-barras horizontais da composição da carteira do fundo."""
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
            pct_txt = _fmt_pct(pct)
            barra = (
                f"<div style='background:#E3E8EF;border-radius:4px;height:14px;"
                f"width:100%;margin-top:2px;'>"
                f"<div style='background:{COR_PRIMARIA};height:14px;border-radius:4px;"
                f"width:{largura}%;'></div></div>"
            )
            linhas.append(
                f"<div style='margin:5px 0;'>"
                f"<table role='presentation' width='100%' cellpadding='0' cellspacing='0'><tr>"
                f"<td style='font-family:Arial,sans-serif;font-size:12px;color:#333;'>{nome}</td>"
                f"<td align='right' style='font-family:Arial,sans-serif;font-size:12px;"
                f"color:#5A6B7B;font-weight:bold;'>{pct_txt}</td></tr></table>{barra}</div>"
            )
        else:
            # sem percentual: só lista o item
            linhas.append(
                f"<div style='font-family:Arial,sans-serif;font-size:12px;color:#333;"
                f"margin:4px 0;'>• {nome}</div>"
            )
    if not linhas:
        return ""
    return (
        f"<div style='margin-top:10px;'>"
        f"<div style='font-family:Arial,sans-serif;font-size:12px;font-weight:bold;"
        f"color:{COR_PRIMARIA};margin-bottom:2px;'>📦 Composição</div>"
        f"{''.join(linhas)}</div>"
    )


def _bloco_texto(titulo, texto, separar_ponto_virgula=False):
    """Bloco de texto opcional (vantagens / tese)."""
    texto = (texto or "").strip()
    if not texto:
        return ""
    if separar_ponto_virgula:
        itens = [t.strip() for t in texto.split(";") if t.strip()]
        corpo = "".join(
            f"<div style='font-family:Arial,sans-serif;font-size:13px;color:#333;"
            f"margin:3px 0;line-height:1.5;'>✓ {it}</div>" for it in itens
        )
    else:
        corpo = (f"<div style='font-family:Arial,sans-serif;font-size:13px;color:#333;"
                 f"line-height:1.5;'>{texto}</div>")
    return (
        f"<div style='margin-top:10px;'>"
        f"<div style='font-family:Arial,sans-serif;font-size:12px;font-weight:bold;"
        f"color:{COR_PRIMARIA};margin-bottom:2px;'>{titulo}</div>{corpo}</div>"
    )


def _card_oportunidade(ticker, d):
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

    composicao = _barras_composicao(d.get("composicao"))
    vantagens = _bloco_texto("⭐ Vantagens", d.get("vantagens"), separar_ponto_virgula=True)
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
        f"{composicao}"
        f"{vantagens}"
        f"{tese}"
        f"</div>"
    )


def montar_html(atrativos):
    hoje = datetime.now().strftime("%d/%m/%Y")
    # ordena por P/VP crescente
    atrativos.sort(key=lambda x: (_num(x["dados"].get("pvp")) is None,
                                  _num(x["dados"].get("pvp")) or 999))
    cards = "".join(_card_oportunidade(a["ticker"], a["dados"]) for a in atrativos)

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
          <div style="font-family:Arial,sans-serif;font-size:13px;color:#5A6B7B;
                      margin-bottom:6px;">FIIs da sua carteira que aparecem atrativos hoje,
            por P/VP, posição vs mínima de 52 semanas e DY. Ordenados por P/VP.</div>
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


def enviar_email(html):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🎯 Oportunidades de FIIs — {datetime.now().strftime('%d/%m')}"
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
        print(f"ERRO: variáveis faltando: {', '.join(faltando)}")
        sys.exit(1)

    print(f"Avaliando oportunidades em {len(FIIS)} FIIs...")
    resultados = {}
    pendentes = list(FIIS)

    for rodada in range(1, MAX_RODADAS + 1):
        if not pendentes:
            break
        if rodada > 1:
            print(f"\n--- Rodada {rodada}: re-tentando {len(pendentes)} com 429 ---")
        ainda_429 = []
        for i, ticker in enumerate(pendentes, 1):
            print(f"[rodada {rodada}] [{i}/{len(pendentes)}] {ticker}...")
            r = avaliar_fii(ticker)
            if "dados" in r:
                resultados[ticker] = r
                print(f"  -> {r['dados'].get('nota','?')}")
            elif r.get("rate_limited"):
                resultados[ticker] = r
                ainda_429.append(ticker)
                print("  -> 429 (re-tentar)")
            else:
                resultados[ticker] = r
                print(f"  -> ERRO: {r['erro']}")
            time.sleep(PAUSA_ENTRE_FIIS)
        pendentes = ainda_429
        if pendentes and rodada < MAX_RODADAS:
            print(f"\nAguardando {ESPERA_RODADA}s antes da próxima rodada...")
            time.sleep(ESPERA_RODADA)

    # Filtra só os atrativos
    atrativos = []
    for t in FIIS:
        r = resultados.get(t)
        if r and "dados" in r:
            nota = (r["dados"].get("nota") or "").strip().lower()
            if "atrativo" in nota:
                atrativos.append(r)

    if not atrativos:
        print("Nenhuma oportunidade atrativa hoje. E-mail NÃO enviado.")
        return

    print(f"\n{len(atrativos)} oportunidade(s) encontrada(s). Enviando e-mail...")
    html = montar_html(atrativos)
    try:
        enviar_email(html)
        print(f"E-mail enviado para {EMAIL_TO}")
    except Exception as e:
        print(f"ERRO ao enviar e-mail: {e}")
        with open("oportunidades_falhou.html", "w", encoding="utf-8") as f:
            f.write(html)
        sys.exit(1)


if __name__ == "__main__":
    main()
