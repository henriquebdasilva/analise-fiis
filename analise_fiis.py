#!/usr/bin/env python3
"""
Análise mensal de FIIs via Gemini (com grounding/busca) + envio por e-mail.

Roda sem scraping: o próprio Gemini pesquisa na web os dados de cada FII.
Projetado para rodar no GitHub Actions (mensal) ou localmente.

Variáveis de ambiente necessárias (configuradas como Secrets no GitHub):
  GEMINI_API_KEY      -> chave da API Gemini (aistudio.google.com)
  GMAIL_USER          -> seu e-mail Gmail (remetente)
  GMAIL_APP_PASSWORD  -> senha de app de 16 dígitos (não a senha normal!)
  EMAIL_TO            -> (opcional) destinatário; se omitido, usa GMAIL_USER
  FIIS                -> (opcional) lista separada por vírgula; se omitido, usa a lista padrão
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
EMAIL_TO = os.environ.get("EMAIL_TO", "").strip() or GMAIL_USER

MODEL = "gemini-2.5-flash"
API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{MODEL}:generateContent"
)

# Carteira padrão (16 FIIs). Pode sobrescrever via env FIIS="MXRF11,KNCR11,..."
DEFAULT_FIIS = [
    "MXRF11", "KNCR11", "KNSC11", "RBRR11", "MCCI11",
    "HGLG11", "BRCO11", "BTLG11", "XPLG11",
    "HGBS11", "XPML11", "HSML11",
    "TRXF11", "HGRU11", "KNRI11", "RBRX11",
]

_env_fiis = os.environ.get("FIIS", "").strip()
FIIS = [t.strip().upper() for t in _env_fiis.split(",") if t.strip()] if _env_fiis else DEFAULT_FIIS

PAUSA_ENTRE_FIIS = 3      # segundos entre chamadas (respeita rate limit)
MAX_RETRIES = 3           # tentativas em caso de rate limit
RETRY_BACKOFF = 20        # segundos de espera entre retries


# ----------------------------------------------------------------------
# Análise de um FII via Gemini (com grounding/busca no Google)
# ----------------------------------------------------------------------
def analisar_fii(ticker: str) -> dict:
    """Retorna {'ticker', 'resumo'} em caso de sucesso, ou {'ticker', 'erro'}."""
    prompt = (
        f"Pesquise dados públicos ATUAIS sobre o fundo imobiliário brasileiro {ticker} "
        f"(use o relatório gerencial mais recente, Status Invest, Funds Explorer). "
        f"Escreva um resumo objetivo em português, em no máximo 140 palavras, com:\n"
        f"- DY (dividend yield) dos últimos 12 meses\n"
        f"- P/VP atual\n"
        f"- Vacância (se for fundo de tijolo) ou qualidade da carteira (se for papel/FoF)\n"
        f"- 2 pontos positivos do último relatório\n"
        f"- 2 riscos ou pontos de atenção\n"
        f"- Uma frase de avaliação geral\n\n"
        f"Use texto corrido com marcadores simples. Não invente dados: "
        f"se não encontrar algo, escreva 'não disponível'."
    )

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],  # grounding: o Gemini busca na web
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 2000,
            # Desliga "thinking" para o budget de tokens ir todo para a resposta
            # (evita o truncamento que vimos antes)
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }

    headers = {"Content-Type": "application/json"}
    params = {"key": GEMINI_API_KEY}

    for tentativa in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(
                API_URL, headers=headers, params=params,
                data=json.dumps(payload), timeout=120
            )
        except Exception as e:
            return {"ticker": ticker, "erro": f"Falha de conexão: {e}"}

        if resp.status_code == 429:
            if tentativa < MAX_RETRIES:
                print(f"  [{ticker}] rate limit (429), aguardando {RETRY_BACKOFF}s...")
                time.sleep(RETRY_BACKOFF)
                continue
            return {"ticker": ticker, "erro": "Rate limit persistente (429)"}

        if resp.status_code != 200:
            detalhe = resp.text[:200]
            return {"ticker": ticker, "erro": f"HTTP {resp.status_code}: {detalhe}"}

        try:
            data = resp.json()
            cand = data["candidates"][0]
            finish = cand.get("finishReason", "")
            if finish == "MAX_TOKENS":
                return {"ticker": ticker, "erro": "Resposta truncada (MAX_TOKENS)"}
            texto = cand["content"]["parts"][0]["text"].strip()
            if not texto:
                return {"ticker": ticker, "erro": "Resposta vazia"}
            return {"ticker": ticker, "resumo": texto}
        except (KeyError, IndexError) as e:
            return {"ticker": ticker, "erro": f"Resposta inesperada: {e} | {resp.text[:150]}"}

    return {"ticker": ticker, "erro": "Falhou após retries"}


# ----------------------------------------------------------------------
# Montagem do e-mail (HTML)
# ----------------------------------------------------------------------
def montar_html(resultados: list) -> str:
    hoje = datetime.now().strftime("%d/%m/%Y")
    sucesso = sum(1 for r in resultados if "resumo" in r)
    falha = len(resultados) - sucesso

    blocos = []
    for r in resultados:
        ticker = r["ticker"]
        if "resumo" in r:
            # converte quebras de linha simples em <br> e marcadores em itens
            corpo = r["resumo"].replace("\n", "<br>")
            cor_borda = "#2E75B6"
            conteudo = corpo
        else:
            cor_borda = "#C00000"
            conteudo = f"<span style='color:#C00000'>⚠️ {r['erro']}</span>"

        blocos.append(f"""
        <div style="border-left:4px solid {cor_borda}; padding:10px 16px; margin:14px 0;
                    background:#f8f9fb; border-radius:4px;">
          <h3 style="margin:0 0 8px 0; color:#1F4E78; font-family:Arial,sans-serif;">{ticker}</h3>
          <div style="font-family:Arial,sans-serif; font-size:14px; color:#333; line-height:1.5;">
            {conteudo}
          </div>
        </div>
        """)

    return f"""
    <html><body style="background:#ffffff; padding:0; margin:0;">
      <div style="max-width:680px; margin:0 auto; padding:20px;">
        <h1 style="font-family:Arial,sans-serif; color:#1F4E78;">
          📊 Análise Mensal da Carteira de FIIs
        </h1>
        <p style="font-family:Arial,sans-serif; color:#555; font-size:14px;">
          Gerado em {hoje} · {sucesso} analisado(s) com sucesso · {falha} com erro<br>
          <em>Fonte: Gemini com busca na web. Confira sempre antes de decidir —
          isto não é recomendação de investimento.</em>
        </p>
        {''.join(blocos)}
        <hr style="border:none; border-top:1px solid #ddd; margin:24px 0;">
        <p style="font-family:Arial,sans-serif; color:#999; font-size:12px;">
          E-mail automático gerado pelo seu robô de análise de FIIs.
        </p>
      </div>
    </body></html>
    """


# ----------------------------------------------------------------------
# Envio de e-mail via Gmail SMTP
# ----------------------------------------------------------------------
def enviar_email(html: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"📊 Análise dos FIIs — {datetime.now().strftime('%B/%Y')}"
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
    # Validação das variáveis de ambiente
    faltando = [v for v in ["GEMINI_API_KEY", "GMAIL_USER", "GMAIL_APP_PASSWORD"]
                if not os.environ.get(v, "").strip()]
    if faltando:
        print(f"ERRO: variáveis de ambiente faltando: {', '.join(faltando)}")
        sys.exit(1)

    print(f"Analisando {len(FIIS)} FIIs: {', '.join(FIIS)}")
    resultados = []
    for i, ticker in enumerate(FIIS, 1):
        print(f"[{i}/{len(FIIS)}] {ticker}...")
        r = analisar_fii(ticker)
        if "erro" in r:
            print(f"  -> ERRO: {r['erro']}")
        else:
            print(f"  -> OK ({len(r['resumo'])} chars)")
        resultados.append(r)
        if i < len(FIIS):
            time.sleep(PAUSA_ENTRE_FIIS)

    print("Montando e enviando e-mail...")
    html = montar_html(resultados)
    try:
        enviar_email(html)
        print(f"E-mail enviado para {EMAIL_TO}")
    except Exception as e:
        print(f"ERRO ao enviar e-mail: {e}")
        # Salva o HTML como artefato para debug
        with open("analise_falhou.html", "w", encoding="utf-8") as f:
            f.write(html)
        sys.exit(1)


if __name__ == "__main__":
    main()
