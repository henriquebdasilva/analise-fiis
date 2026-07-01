#!/usr/bin/env python3
"""
Robô de FIIs — script principal com modos (#4).

Uso:
  python robo.py --modo mensal         # relatório completo (1x/mês)
  python robo.py --modo oportunidades  # radar de oportunidades (1x/dia)
  python robo.py --modo alertas        # alertas de variação brusca (1x/dia)

Todos os modos compartilham os módulos de core/ (config, gemini, e-mail, histórico).
Inclui resiliência (#3): valida credenciais, verifica o dia (modo mensal),
registra histórico (#1) e envia "heartbeat" se a execução não obtiver dados.
"""
import argparse
import sys
from datetime import datetime

from core.config import Config, carregar_fiis
from core.gemini import analisar_carteira
from core.email_sender import enviar_email
from core.historico import registrar

from relatorios import mensal, oportunidades, alertas


def _heartbeat(cfg, modo, motivo):
    """#3 — avisa que o robô rodou mas não produziu resultado, para você saber
    que está vivo (e não achar que esqueceu de rodar)."""
    hoje = datetime.now().strftime("%d/%m/%Y %H:%M")
    html = (
        f"<div style='font-family:Arial,sans-serif;max-width:520px;margin:auto;padding:20px;'>"
        f"<h2 style='color:#1F4E78;'>🤖 Robô de FIIs — {modo}</h2>"
        f"<p style='color:#333;font-size:14px;line-height:1.6;'>O robô rodou em {hoje}, "
        f"mas <strong>não gerou e-mail de conteúdo</strong> desta vez.</p>"
        f"<p style='color:#5A6B7B;font-size:13px;'>Motivo: {motivo}</p>"
        f"<p style='color:#94A3B8;font-size:12px;'>Isto é só um aviso de saúde do robô. "
        f"Se acontecer sempre, verifique a chave da API e os limites do Gemini.</p></div>"
    )
    try:
        enviar_email(f"🤖 Robô de FIIs ({modo}) — sem conteúdo hoje", html, cfg)
        print("Heartbeat enviado.")
    except Exception as e:
        print(f"Falha ao enviar heartbeat: {e}")


def _tem_algum_dado(resultados):
    return any("dados" in r for r in resultados.values())


def rodar_mensal(cfg, fiis, forcar=False):
    # Verificação de dia: só no agendamento (schedule); manual/local roda sempre
    import os
    evento = os.environ.get("GITHUB_EVENT_NAME", "")
    if evento == "schedule" and not forcar:
        if datetime.now().day != cfg.dia_do_mes:
            print(f"Hoje não é dia {cfg.dia_do_mes}; modo mensal não roda (schedule). Saindo.")
            return
    print(f"== MODO MENSAL == {len(fiis)} FIIs")
    resultados = analisar_carteira(
        fiis, mensal.montar_prompt, cfg.gemini_api_key, cfg.model, cfg.pausa_segundos,
        max_tokens=4000)
    registrar(resultados)  # #1
    if not _tem_algum_dado(resultados):
        _heartbeat(cfg, "mensal", "Nenhum FII retornou dados (possível rate limit ou API).")
        return
    html, imagens = mensal.montar_html(resultados, cfg)
    assunto = f"📊 Análise da Carteira de FIIs — {datetime.now().strftime('%m/%Y')}"
    enviar_email(assunto, html, cfg, imagens)
    print(f"Relatório mensal enviado para {cfg.email_to}")


def rodar_oportunidades(cfg, fiis):
    print(f"== MODO OPORTUNIDADES == {len(fiis)} FIIs")
    resultados = analisar_carteira(
        fiis, oportunidades.montar_prompt, cfg.gemini_api_key, cfg.model,
        cfg.pausa_segundos, max_tokens=3000)
    registrar(resultados)  # #1
    if not _tem_algum_dado(resultados):
        _heartbeat(cfg, "oportunidades", "Nenhum FII retornou dados.")
        return
    atrativos = oportunidades.filtrar_atrativos(resultados, fiis)
    if not atrativos:
        print("Nenhuma oportunidade atrativa hoje. E-mail não enviado.")
        return
    html = oportunidades.montar_html(atrativos, cfg)
    assunto = f"🎯 Oportunidades de FIIs — {datetime.now().strftime('%d/%m')}"
    enviar_email(assunto, html, cfg)
    print(f"Radar enviado ({len(atrativos)} oportunidades) para {cfg.email_to}")


def rodar_alertas(cfg, fiis):
    print(f"== MODO ALERTAS == {len(fiis)} FIIs")
    resultados = analisar_carteira(
        fiis, alertas.montar_prompt, cfg.gemini_api_key, cfg.model,
        cfg.pausa_segundos, max_tokens=1000)
    lista = alertas.detectar_alertas(resultados, cfg)  # compara ANTES de registrar
    registrar(resultados)  # #1 (registra depois, para não comparar com o próprio dia)
    if not lista:
        print("Nenhum alerta relevante hoje. E-mail não enviado.")
        return
    html = alertas.montar_html(lista, cfg)
    assunto = f"⚠️ Alertas de FIIs — {datetime.now().strftime('%d/%m')}"
    enviar_email(assunto, html, cfg)
    print(f"Alertas enviados ({len(lista)} FIIs) para {cfg.email_to}")


def main():
    parser = argparse.ArgumentParser(description="Robô de FIIs")
    parser.add_argument("--modo", required=True,
                        choices=["mensal", "oportunidades", "alertas"])
    parser.add_argument("--forcar", action="store_true",
                        help="ignora a verificação de dia no modo mensal")
    args = parser.parse_args()

    cfg = Config()
    faltando = cfg.validar_credenciais()
    if faltando:
        print(f"ERRO: variáveis faltando: {', '.join(faltando)}")
        sys.exit(1)

    fiis = carregar_fiis()

    try:
        if args.modo == "mensal":
            rodar_mensal(cfg, fiis, forcar=args.forcar)
        elif args.modo == "oportunidades":
            rodar_oportunidades(cfg, fiis)
        elif args.modo == "alertas":
            rodar_alertas(cfg, fiis)
    except Exception as e:
        print(f"ERRO na execução ({args.modo}): {e}")
        # #3 — em caso de erro inesperado, tenta avisar
        _heartbeat(cfg, args.modo, f"Erro inesperado: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
