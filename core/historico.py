"""Histórico das análises (#1).

Salva um registro por FII a cada execução num CSV dentro do repositório
(data,ticker,cota,pvp,dy). O workflow faz commit do arquivo, então o histórico
persiste entre execuções e vai crescendo — virando uma base própria e confiável,
independente da memória da IA.

Também expõe leitura para os alertas de variação (#2).
"""
import csv
import os
from datetime import datetime

from core.config import RAIZ
from core.util import _num

ARQUIVO_HISTORICO = os.path.join(RAIZ, "historico.csv")
CABECALHO = ["data", "ticker", "cota", "pvp", "dy"]


def registrar(resultados):
    """Acrescenta uma linha por FII com dados válidos. `resultados` é o dict
    {ticker: {"dados": {...}}} devolvido por analisar_carteira."""
    hoje = datetime.now().strftime("%Y-%m-%d")
    existe = os.path.exists(ARQUIVO_HISTORICO)
    linhas = []
    for ticker, r in resultados.items():
        d = r.get("dados")
        if not d:
            continue
        cota = _num(d.get("cota_atual"))
        pvp = _num(d.get("pvp"))
        dy = _num(d.get("dy_12m"))
        if cota is None and pvp is None and dy is None:
            continue
        linhas.append([hoje, ticker,
                       "" if cota is None else f"{cota:.4f}",
                       "" if pvp is None else f"{pvp:.4f}",
                       "" if dy is None else f"{dy:.6f}"])
    if not linhas:
        print("Histórico: nada válido para registrar.")
        return 0
    with open(ARQUIVO_HISTORICO, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if not existe:
            w.writerow(CABECALHO)
        w.writerows(linhas)
    print(f"Histórico: {len(linhas)} registros gravados em historico.csv")
    return len(linhas)


def ler_historico():
    """Retorna lista de dicts do histórico (ou [] se não existir)."""
    if not os.path.exists(ARQUIVO_HISTORICO):
        return []
    with open(ARQUIVO_HISTORICO, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def ultimo_registro_anterior(ticker, antes_de=None):
    """Retorna o registro mais recente de um ticker (opcionalmente antes de uma data
    YYYY-MM-DD), para comparar com o valor atual nos alertas."""
    regs = [r for r in ler_historico() if r["ticker"] == ticker]
    if antes_de:
        regs = [r for r in regs if r["data"] < antes_de]
    if not regs:
        return None
    regs.sort(key=lambda r: r["data"])
    return regs[-1]
