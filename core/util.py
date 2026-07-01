"""Utilitários compartilhados: parsing de números e formatação BR."""


def _num(v):
    """Converte texto ou número para float, tolerante a formato BR.
    Aceita 'R$ 102,50', '11,5%', '1.234,56', 102.5, etc. Retorna None se não der."""
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


def _fmt_pct(v, casas=1):
    v = _num(v)
    if v is None:
        return "—"
    return f"{v * 100:.{casas}f}%".replace(".", ",")


def _fmt_num(v, casas=2):
    v = _num(v)
    if v is None:
        return "—"
    return f"{v:.{casas}f}".replace(".", ",")


def _fmt_money(v, casas=2):
    v = _num(v)
    if v is None:
        return "—"
    return f"R$ {v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _extrair_json(texto):
    """Extrai o primeiro objeto JSON de um texto (do primeiro { ao último })."""
    import json
    ini = texto.find("{")
    fim = texto.rfind("}")
    if ini == -1 or fim == -1:
        return None
    try:
        return json.loads(texto[ini:fim + 1])
    except json.JSONDecodeError:
        return None
