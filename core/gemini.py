"""Cliente do Gemini: chamada única e orquestração com retry em rodadas.

Reaproveita a estratégia validada nos scripts originais: uma tentativa por FII,
FIIs com 429 são re-tentados em rodadas com espera entre elas.
"""
import json
import time

import requests

from core.util import _extrair_json

ESPERA_RODADA = 120
MAX_RODADAS = 6


def _url(model):
    return ("https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent")


def chamar_gemini(prompt, api_key, model, max_tokens=3000, com_busca=True):
    """Uma chamada ao Gemini. Retorna dict:
       {"dados": {...}} | {"erro": str, "rate_limited": bool}"""
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "thinkingConfig": {"thinkingBudget": 0},
            "maxOutputTokens": max_tokens,
        },
    }
    if com_busca:
        payload["tools"] = [{"google_search": {}}]

    try:
        resp = requests.post(
            _url(model),
            headers={"Content-Type": "application/json"},
            params={"key": api_key},
            data=json.dumps(payload),
            timeout=120,
        )
    except Exception as e:
        return {"erro": f"Conexão: {e}"}

    if resp.status_code == 429:
        return {"erro": "Rate limit (429)", "rate_limited": True}
    if resp.status_code != 200:
        return {"erro": f"HTTP {resp.status_code}"}

    try:
        cand = resp.json()["candidates"][0]
        if cand.get("finishReason") == "MAX_TOKENS":
            return {"erro": "Resposta truncada (MAX_TOKENS)"}
        texto = cand["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        return {"erro": f"Resposta inesperada: {e}"}

    dados = _extrair_json(texto)
    if dados is None:
        return {"erro": "JSON inválido"}
    return {"dados": dados}


def analisar_carteira(fiis, montar_prompt, api_key, model, pausa, max_tokens=3000):
    """Analisa todos os FIIs com retry em rodadas.

    montar_prompt(ticker) -> str é uma função que devolve o prompt de cada FII.
    Retorna dict {ticker: {"ticker", "dados"|"erro", ...}} na ordem de `fiis`.
    """
    resultados = {}
    pendentes = list(fiis)

    for rodada in range(1, MAX_RODADAS + 1):
        if not pendentes:
            break
        if rodada > 1:
            print(f"\n--- Rodada {rodada}: re-tentando {len(pendentes)} FIIs (429) ---")
        ainda_429 = []
        for i, ticker in enumerate(pendentes, 1):
            print(f"[rodada {rodada}] [{i}/{len(pendentes)}] {ticker}...")
            r = chamar_gemini(montar_prompt(ticker), api_key, model, max_tokens)
            r["ticker"] = ticker
            if "dados" in r:
                resultados[ticker] = r
                print("  -> ok")
            elif r.get("rate_limited"):
                resultados[ticker] = r
                ainda_429.append(ticker)
                print("  -> 429 (re-tentar)")
            else:
                resultados[ticker] = r
                print(f"  -> ERRO: {r['erro']}")
            time.sleep(pausa)
        pendentes = ainda_429
        if pendentes and rodada < MAX_RODADAS:
            print(f"\nAguardando {ESPERA_RODADA}s antes da próxima rodada...")
            time.sleep(ESPERA_RODADA)

    # devolve na ordem da carteira
    return {t: resultados.get(t, {"ticker": t, "erro": "não processado"}) for t in fiis}
