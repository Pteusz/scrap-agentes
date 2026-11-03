"""Conexão SQLite (modo WAL), migrações versionadas e índice de busca."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

PASTA_MIGRACOES = Path(__file__).parent / "migracoes"


def agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def conectar(caminho: Path) -> sqlite3.Connection:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    # A conexão nasce numa thread do FastAPI e pode ser usada em outra; cada request tem a sua.
    conn = sqlite3.connect(caminho, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def migrar(conn: sqlite3.Connection) -> list[str]:
    """Aplica, em ordem, as migrações .sql ainda não registradas. Devolve as aplicadas."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS versao_schema "
        "(arquivo TEXT PRIMARY KEY, aplicado_em TEXT NOT NULL)"
    )
    feitas = {r["arquivo"] for r in conn.execute("SELECT arquivo FROM versao_schema")}
    aplicadas = []
    for arq in sorted(PASTA_MIGRACOES.glob("*.sql")):
        if arq.name in feitas:
            continue
        conn.executescript(arq.read_text(encoding="utf-8"))
        conn.execute(
            "INSERT INTO versao_schema (arquivo, aplicado_em) VALUES (?, ?)",
            (arq.name, agora_iso()),
        )
        conn.commit()
        aplicadas.append(arq.name)
    return aplicadas


def texto_falado(texto_json: str | None) -> str:
    if not texto_json:
        return ""
    return " ".join(t.get("texto", "") for t in json.loads(texto_json))


def reindexar_busca(conn: sqlite3.Connection, item_id: int) -> None:
    item = conn.execute(
        "SELECT legenda, texto FROM item WHERE id = ?", (item_id,)
    ).fetchone()
    conn.execute("DELETE FROM busca WHERE rowid = ?", (item_id,))
    if item is not None:
        conn.execute(
            "INSERT INTO busca (rowid, legenda, texto) VALUES (?, ?, ?)",
            (item_id, item["legenda"] or "", texto_falado(item["texto"])),
        )
