"""Alertas de variação brusca (#2).

Diferente do radar diário (que sempre envia), este modo só dispara e-mail quando
algo relevante acontece, comparando a cota atual com o último registro do histórico:
  - queda acima de um limiar (ALERTA_QUEDA_PCT, ex: 7%)
  - P/VP cruzou abaixo de um piso (ALERTA_PVP_MAX, ex: 0,90)

Usa a base do histórico (#1), então é preciso e não depende de "memória" da IA.
"""
from datetime import datetime

from core.util import _num, _fmt_pct, _fmt_num, _fmt_money
from core.historico import ultimo_registro_anterior

COR_PRIMARIA = "#1F4E78"
COR_ALERTA = "#C0392B"
COR_OPORT = "#1E7B46"


def montar_prompt(ticker):
    return (
        f"Pesquise os dados ATUAIS do fundo imobiliário brasileiro {ticker} "
        f"(Status Invest, Funds Explorer). Responda APENAS JSON válido, sem markdown, "
        f"usando null quando não tiver certeza (não invente):\n"
        f'{{"cota_atual": <preço atual da cota em reais, decimal, ou null>, '
        f'"pvp": <P/VP atual, decimal, ou null>, '
        f'"dy_12m": <dividend yield 12m, decimal, ou null>}}'
    )


def detectar_alertas(resultados, cfg):
    """Compara os resultados atuais com o histórico e devolve a lista de alertas."""
    alertas = []
    hoje = datetime.now().strftime("%Y-%m-%d")
    for ticker, r in resultados.items():
        d = r.get("dados")
        if not d:
            continue
        cota = _num(d.get("cota_atual"))
        pvp = _num(d.get("pvp"))
        motivos = []

        # Alerta de queda vs último registro anterior
        anterior = ultimo_registro_anterior(ticker, antes_de=hoje)
        if anterior and cota is not None:
            cota_ant = _num(anterior.get("cota"))
            if cota_ant and cota_ant > 0:
                var = (cota - cota_ant) / cota_ant * 100
                if var <= -cfg.alerta_queda_pct:
                    motivos.append({
                        "tipo": "queda",
                        "texto": (f"Caiu {_fmt_num(abs(var))}% desde {anterior['data']} "
                                  f"(de {_fmt_money(cota_ant)} para {_fmt_money(cota)})"),
                    })

        # Alerta de P/VP abaixo do piso
        if pvp is not None and pvp <= cfg.alerta_pvp_max:
            motivos.append({
                "tipo": "pvp",
                "texto": f"P/VP em {_fmt_num(pvp)} (abaixo do piso {_fmt_num(cfg.alerta_pvp_max)})",
            })

        if motivos:
            alertas.append({"ticker": ticker, "cota": cota, "pvp": pvp, "motivos": motivos})
    return alertas


def montar_html(alertas, cfg):
    hoje = datetime.now().strftime("%d/%m/%Y")
    cards = []
    for a in alertas:
        itens = "".join(
            f"<div style='font-family:Arial,sans-serif;font-size:13px;color:#333;"
            f"margin:3px 0;line-height:1.5;'>"
            f"{'📉' if m['tipo']=='queda' else '🏷️'} {m['texto']}</div>"
            for m in a["motivos"]
        )
        cota_txt = _fmt_money(a["cota"]) if a["cota"] is not None else ""
        cards.append(
            f"<div style='padding:12px 0;border-bottom:1px solid #F0D0CC;'>"
            f"<table role='presentation' width='100%' cellpadding='0' cellspacing='0'><tr>"
            f"<td style='font-family:Arial,sans-serif;font-size:16px;font-weight:bold;"
            f"color:{COR_ALERTA};'>⚠️ {a['ticker']}</td>"
            f"<td align='right' style='font-family:Arial,sans-serif;font-size:15px;"
            f"font-weight:bold;color:{COR_PRIMARIA};'>{cota_txt}</td></tr></table>"
            f"<div style='margin-top:4px;'>{itens}</div></div>"
        )

    return f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#EEF1F5;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#EEF1F5;">
    <tr><td align="center" style="padding:24px 12px;">
      <table role="presentation" width="600" cellpadding="0" cellspacing="0"
             style="max-width:600px;width:100%;background:#fff;border-radius:12px;
                    overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,0.08);">
        <tr><td style="background:{COR_ALERTA};padding:22px 28px;">
          <div style="font-family:Arial,sans-serif;color:#fff;font-size:20px;font-weight:bold;">
            ⚠️ Alertas da Carteira de FIIs</div>
          <div style="font-family:Arial,sans-serif;color:#F5C6C0;font-size:13px;margin-top:4px;">
            {hoje} · {len(alertas)} FII(s) merecem atenção</div>
        </td></tr>
        <tr><td style="padding:18px 28px 8px 28px;">
          <div style="font-family:Arial,sans-serif;font-size:13px;color:#5A6B7B;margin-bottom:8px;">
            Movimentos relevantes detectados comparando com o histórico. Vale investigar
            o motivo (pode ser oportunidade ou risco).</div>
          {''.join(cards)}
        </td></tr>
        <tr><td style="padding:8px 28px 24px 28px;">
          <div style="border-top:1px solid #E3E8EF;padding-top:14px;
                      font-family:Arial,sans-serif;font-size:12px;color:#94A3B8;line-height:1.6;">
            Gerado em {hoje}. Baseado no histórico próprio + dados atuais (Gemini com busca).<br>
            ⚠️ Uma queda pode ser oportunidade OU sinal de problema — investigue antes de agir.
            <strong>Não é recomendação de investimento.</strong>
          </div>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""
