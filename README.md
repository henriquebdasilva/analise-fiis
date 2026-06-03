# 📊 Robô de Análise Mensal de FIIs

Analisa automaticamente os relatórios/dados dos seus FIIs uma vez por mês e
envia um resumo por e-mail. **Sem custo, sem scraping frágil, sem servidor próprio.**

Como funciona: um script Python roda na nuvem do GitHub (grátis) todo dia 20.
Para cada FII, ele pergunta ao **Google Gemini** (que busca na web sozinho — por
isso não precisamos baixar PDF nem driblar bloqueios). O resultado vira um
e-mail formatado enviado para você.

---

## ✅ O que você vai precisar (tudo gratuito)

1. Conta no **GitHub** (github.com)
2. Chave da **API do Gemini** (aistudio.google.com)
3. **Senha de app do Gmail** (para o robô enviar e-mail pela sua conta)

---

## 🔧 Passo a passo de instalação

### 1. Pegar a chave do Gemini

1. Acesse **aistudio.google.com** e faça login
2. Clique em **"Get API Key"** → **"Create API key"**
3. Copie a chave (guarde, você vai colar no GitHub depois)

### 2. Gerar a senha de app do Gmail

> A senha de app é diferente da sua senha normal. Ela permite que o script
> envie e-mail pela sua conta com segurança.

1. Ative a **verificação em 2 etapas** na sua Conta Google (se ainda não tiver):
   myaccount.google.com → Segurança → Verificação em duas etapas
2. Depois, acesse: myaccount.google.com/apppasswords
3. Dê um nome (ex: "Robô FIIs") e clique em **Criar**
4. Copie a senha de **16 caracteres** que aparecer (sem espaços)

### 3. Criar o repositório no GitHub

1. Em github.com, clique em **"New repository"**
2. Nome: `analise-fiis` (ou o que preferir). Pode deixar **Privado**.
3. Crie o repositório
4. Faça upload destes arquivos (botão "Add file" → "Upload files"):
   - `analise_fiis.py`
   - `requirements.txt`
   - a pasta `.github/workflows/analise-mensal.yml`
   
   > Dica: para subir a pasta `.github/workflows/`, ao fazer upload digite
   > `.github/workflows/analise-mensal.yml` no nome do arquivo que o GitHub
   > cria as pastas sozinho.

### 4. Configurar os segredos (Secrets)

No seu repositório: **Settings** → **Secrets and variables** → **Actions**
→ botão **"New repository secret"**. Crie um por um:

| Nome do Secret | Valor |
|---|---|
| `GEMINI_API_KEY` | sua chave do Gemini |
| `GMAIL_USER` | seu e-mail Gmail completo |
| `GMAIL_APP_PASSWORD` | a senha de app de 16 caracteres |
| `EMAIL_TO` | (opcional) e-mail destino, se diferente do GMAIL_USER |
| `FIIS` | (opcional) lista personalizada, ex: `MXRF11,KNCR11,HGLG11` |

> Se não criar o `FIIS`, ele usa a carteira padrão de 16 FIIs já embutida no script.

### 5. Testar agora (sem esperar o dia 20)

1. No repositório, aba **"Actions"**
2. Clique em **"Análise Mensal de FIIs"** na lista à esquerda
3. Botão **"Run workflow"** → **"Run workflow"**
4. Aguarde ~2 minutos e veja o log (clique na execução)
5. Confira seu e-mail 📬

---

## 📅 Quando roda automaticamente

Todo **dia 20 de cada mês**, por volta das **9h (horário de Brasília)**.
Para mudar, edite a linha `cron: "0 12 20 * *"` no arquivo
`.github/workflows/analise-mensal.yml` (o horário está em UTC).

---

## 🐛 Se algo der errado

- **Erro de e-mail (autenticação):** confira se usou a *senha de app* (16 dígitos),
  não a senha normal do Gmail. Verifique também se a verificação em 2 etapas está ativa.
- **Erro 429 (rate limit):** o script já tenta de novo sozinho. Se persistir,
  reduza a lista de FIIs ou aumente `PAUSA_ENTRE_FIIS` no script.
- **Erro de chave Gemini:** confira o secret `GEMINI_API_KEY`.
- **Ver o que aconteceu:** aba Actions → clique na execução → veja o log linha a linha.

---

## ⚠️ Avisos

- A IA pode errar ou usar dados levemente defasados. **Sempre confira antes de decidir.**
- Isto **não é recomendação de investimento**.
- O tier gratuito do Gemini cobre folgadamente 16 FIIs/mês (limite de 1.500 buscas/dia).

---

## 💻 Rodar localmente (alternativa ao GitHub)

Se preferir rodar no seu próprio computador:

```bash
pip install -r requirements.txt

export GEMINI_API_KEY="sua_chave"
export GMAIL_USER="seu@gmail.com"
export GMAIL_APP_PASSWORD="senha_de_app_16_digitos"
# opcional:
export EMAIL_TO="destino@email.com"
export FIIS="MXRF11,KNCR11,HGLG11"

python analise_fiis.py
```

No Windows (PowerShell), use `$env:GEMINI_API_KEY="..."` no lugar de `export`.
Para agendar mensalmente: Agendador de Tarefas (Windows) ou cron (Mac/Linux).
