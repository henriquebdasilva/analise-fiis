"""Carregamento de configurações (settings.txt) e da carteira (carteira.txt).

Todos os caminhos são relativos à raiz do projeto (pasta que contém este pacote).
"""
import os

# Raiz do projeto = pasta acima de core/
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ARQUIVO_SETTINGS = os.path.join(RAIZ, "settings.txt")
ARQUIVO_CARTEIRA = os.path.join(RAIZ, "carteira.txt")

DEFAULT_FIIS = [
    "MXRF11", "KNCR11", "KNSC11", "RBRR11", "MCCI11",
    "HGLG11", "BRCO11", "BTLG11", "XPLG11",
    "HGBS11", "XPML11", "HSML11",
    "TRXF11", "HGRU11", "KNRI11", "RBRX11",
]


def carregar_settings():
    """Lê settings.txt no formato CHAVE=valor. Retorna dict (chaves em maiúsculas)."""
    settings = {}
    if os.path.exists(ARQUIVO_SETTINGS):
        with open(ARQUIVO_SETTINGS, "r", encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if not linha or linha.startswith("#") or "=" not in linha:
                    continue
                chave, _, valor = linha.partition("=")
                settings[chave.strip().upper()] = valor.split("#")[0].strip()
    return settings


def carregar_fiis():
    """Retorna a lista de FIIs: env FIIS > carteira.txt > lista padrão embutida."""
    env = os.environ.get("FIIS", "").strip()
    if env:
        return [t.strip().upper() for t in env.replace("\n", ",").split(",") if t.strip()]
    if os.path.exists(ARQUIVO_CARTEIRA):
        fiis = []
        with open(ARQUIVO_CARTEIRA, "r", encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if linha and not linha.startswith("#"):
                    fiis.append(linha.upper())
        if fiis:
            print(f"Carteira: lida de carteira.txt ({len(fiis)} FIIs)")
            return fiis
    print(f"Carteira: usando lista padrão embutida ({len(DEFAULT_FIIS)} FIIs)")
    return DEFAULT_FIIS


class Config:
    """Configuração consolidada, lida de env + settings.txt."""

    def __init__(self):
        s = carregar_settings()
        self.settings = s
        self.gemini_api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        self.gmail_user = os.environ.get("GMAIL_USER", "").strip()
        self.gmail_app_password = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
        self.email_to = (os.environ.get("EMAIL_TO", "").strip()
                         or s.get("EMAIL_TO", "").strip()
                         or self.gmail_user)
        self.model = s.get("MODEL", "").strip() or "gemini-2.5-flash-lite"
        try:
            self.dia_do_mes = int(s.get("DIA_DO_MES", "20"))
        except ValueError:
            self.dia_do_mes = 20
        try:
            self.pausa_segundos = int(s.get("PAUSA_SEGUNDOS", "20"))
        except ValueError:
            self.pausa_segundos = 20
        # Alertas (#2): limiares configuráveis
        try:
            self.alerta_queda_pct = float(s.get("ALERTA_QUEDA_PCT", "7"))
        except ValueError:
            self.alerta_queda_pct = 7.0
        try:
            self.alerta_pvp_max = float(s.get("ALERTA_PVP_MAX", "0.90"))
        except ValueError:
            self.alerta_pvp_max = 0.90

    def validar_credenciais(self):
        faltando = []
        if not self.gemini_api_key:
            faltando.append("GEMINI_API_KEY")
        if not self.gmail_user:
            faltando.append("GMAIL_USER")
        if not self.gmail_app_password:
            faltando.append("GMAIL_APP_PASSWORD")
        return faltando
