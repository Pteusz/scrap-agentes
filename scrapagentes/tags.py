"""Normalização de tags (SPEC, seção 3): minúsculas, sem acento, espaços aparados e colapsados."""
import re
import unicodedata


def normalizar_tag(texto: str) -> str:
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)
    )
    return re.sub(r"\s+", " ", sem_acento.strip().lower())


def normalizar_tags(tags) -> list[str]:
    """Normaliza, descarta vazias e remove repetidas, mantendo a ordem."""
    vistas: dict[str, None] = {}
    for t in tags or []:
        n = normalizar_tag(str(t))
        if n:
            vistas.setdefault(n, None)
    return list(vistas)
