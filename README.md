# 🤖 Robô de FIIs — versão modular

Robô que analisa sua carteira de FIIs com IA (Google Gemini + busca na web) e
envia relatórios por e-mail. Reformulado em módulos, com 3 modos e histórico próprio.

## Modos (um robô, três funções)

```bash
python robo.py --modo mensal         # relatório completo (1x/mês, no DIA_DO_MES)
python robo.py --modo oportunidades  # radar de oportunidades de compra (1x/dia)
python robo.py --modo alertas        # alertas de variação brusca (dias úteis)
```

| Modo | O que faz | Quando envia e-mail |
|---|---|---|
| **mensal** | Análise detalhada de cada FII (cards, gráficos, inquilinos, indexadores) + 📌 resumo executivo no topo | Sempre (no dia configurado) |
| **oportunidades** | Só os FIIs atrativos hoje (P/VP, mín. 52s, DY, composição, vantagens, tese, **comparação com o setor**) | Só se houver algum atrativo |
| **alertas** | Detecta quedas fortes e P/VP abaixo do piso, comparando com o **histórico próprio** | Só se houver algum alerta |

## Estrutura

```
robo.py                      ← ponto de entrada (--modo)
core/
  config.py                  ← settings.txt, carteira.txt, credenciais
  gemini.py                  ← chamada à IA + retry em rodadas (anti-429)
  util.py                    ← parsing/formatação BR
  email_sender.py            ← envio via Gmail
  historico.py               ← grava/lê historico.csv (base própria de dados)
relatorios/
  mensal.py                  ← relatório completo + resumo executivo
  oportunidades.py           ← radar + comparação com setor
  alertas.py                 ← alertas de variação
carteira.txt, settings.txt   ← configuração
historico.csv                ← criado/atualizado automaticamente
.github/workflows/           ← mensal.yml, oportunidades.yml, alertas.yml
```

## As 6 melhorias

1. **Histórico** — cada execução grava cota/P/VP/DY em `historico.csv`, commitado
   pelo próprio workflow. Vira uma base própria e confiável ao longo do tempo.
2. **Alertas de variação** — modo `alertas` só te avisa quando algo relevante
   acontece (queda > `ALERTA_QUEDA_PCT`% ou P/VP <= `ALERTA_PVP_MAX`).
3. **Resiliência** — se nenhum FII retornar dados (ex: rate limit total), envia um
   e-mail curto de "heartbeat" avisando, em vez de silêncio. Erros inesperados
   também disparam aviso.
4. **Consolidação** — um só `robo.py` com modos; código compartilhado em `core/`.
5. **Comparação com o setor** — no radar, mostra se o P/VP do fundo está acima/
   abaixo da média do segmento dele.
6. **Resumo executivo** — parágrafo no topo do relatório mensal (nº de FIIs,
   maior DY, menor P/VP, quantos abaixo do VP).

## Configuração (settings.txt)

```
EMAIL_TO=              # em branco = usa o próprio Gmail
DIA_DO_MES=20          # dia do relatório mensal
MODEL=gemini-2.5-flash-lite
PAUSA_SEGUNDOS=20      # pausa entre FIIs (anti-429)
ALERTA_QUEDA_PCT=7     # queda que dispara alerta
ALERTA_PVP_MAX=0.90    # P/VP que dispara alerta
```

Secrets do GitHub (Settings → Secrets → Actions): `GEMINI_API_KEY`, `GMAIL_USER`,
`GMAIL_APP_PASSWORD`, `EMAIL_TO` (opcional), `FIIS` (opcional).

## Instalação no GitHub

1. Suba a pasta inteira para o repositório (mantendo a estrutura de pastas).
2. Confirme os secrets.
3. Os 3 workflows aparecem na aba **Actions**; teste cada um com **Run workflow**.

## Observações honestas

- Os dados vêm da IA com busca na web — P/VP, mínimas e composição podem ter
  imprecisões. Use como ponto de partida; confira no Status Invest.
- O modo **alertas** precisa de pelo menos 2 execuções para ter histórico e
  detectar quedas (a 1ª só popula a base).
- ⚠️ Não é recomendação de investimento.
