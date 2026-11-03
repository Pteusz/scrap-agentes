"""Backup do banco (cópia consistente pelo mecanismo próprio do SQLite) e da pasta de mídia.

    python -m scrapagentes.backup                      # cria um backup e apaga os antigos
    python -m scrapagentes.backup --verificar PASTA    # restaura numa pasta temporária e confere

Cada backup é uma pasta `backup-AAAAMMDD-HHMMSS` em `--destino` com `scrapagentes.sqlite` e `midia/`.
O banco vai primeiro; a mídia depois, sem as pastas `.novo` (troca ainda em curso). Uma mídia que
estivesse sendo trocada nesse instante fica de fora: o item é refeito na próxima ingestão.
"""
import argparse
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

PREFIXO = "backup-"
FORMATO = "%Y%m%d-%H%M%S"


def criar(dados: Path, destino: Path, manter_dias: int = 7, agora: datetime | None = None) -> Path:
    agora = agora or datetime.now()
    banco = dados / "scrapagentes.sqlite"
    if not banco.is_file():
        raise FileNotFoundError(f"banco não encontrado em {banco}")
    destino.mkdir(parents=True, exist_ok=True)
    final = destino / f"{PREFIXO}{agora.strftime(FORMATO)}"
    parcial = destino / f"{final.name}.parcial"
    shutil.rmtree(parcial, ignore_errors=True)
    parcial.mkdir()
    try:
        origem = sqlite3.connect(banco, timeout=60)
        copia = sqlite3.connect(parcial / "scrapagentes.sqlite")
        try:
            origem.backup(copia)  # consistente mesmo com a API e o worker escrevendo (WAL)
            if copia.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("a cópia do banco não passou no integrity_check")
        finally:
            copia.close()
            origem.close()
        midia = dados / "midia"
        if midia.is_dir():
            shutil.copytree(midia, parcial / "midia", ignore=shutil.ignore_patterns("*.novo"))
        else:
            (parcial / "midia").mkdir()
        parcial.rename(final)
    except BaseException:
        shutil.rmtree(parcial, ignore_errors=True)
        raise
    podar(destino, manter_dias, agora)
    return final


def podar(destino: Path, manter_dias: int, agora: datetime) -> list[Path]:
    limite = agora - timedelta(days=manter_dias)
    apagados = []
    for pasta in sorted(destino.glob(f"{PREFIXO}*")):
        if pasta.suffix == ".parcial" or not pasta.is_dir():
            continue
        try:
            quando = datetime.strptime(pasta.name[len(PREFIXO):], FORMATO)
        except ValueError:
            continue
        if quando < limite:
            shutil.rmtree(pasta)
            apagados.append(pasta)
    return apagados


def verificar(backup: Path) -> dict:
    """Restaura o backup numa pasta temporária, abre o banco e confere itens, imagens e arquivos."""
    with tempfile.TemporaryDirectory(prefix="restauracao-") as tmp:
        restaurado = Path(tmp) / "dados"
        shutil.copytree(backup, restaurado)
        conn = sqlite3.connect(restaurado / "scrapagentes.sqlite")
        try:
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("integrity_check falhou no banco restaurado")
            itens = conn.execute("SELECT COUNT(*) FROM item").fetchone()[0]
            imagens = conn.execute("SELECT COUNT(*) FROM imagem").fetchone()[0]
            metricas = conn.execute("SELECT COUNT(*) FROM metrica").fetchone()[0]
            busca = conn.execute("SELECT COUNT(*) FROM item WHERE legenda IS NOT NULL").fetchone()[0]
        finally:
            conn.close()
        arquivos = sum(1 for p in (restaurado / "midia").rglob("*") if p.is_file())
        return {"itens": itens, "imagens": imagens, "metricas": metricas, "com_legenda": busca,
                "arquivos_de_midia": arquivos}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dados", default=os.environ.get("SCRAPAGENTES_DADOS", "dados"))
    ap.add_argument("--destino", default=os.environ.get("SCRAPAGENTES_BACKUP", "backups"))
    ap.add_argument("--manter-dias", type=int, default=7)
    ap.add_argument("--verificar", metavar="PASTA", help="restaura PASTA em local temporário e confere")
    args = ap.parse_args(argv)
    if args.verificar:
        print(verificar(Path(args.verificar)))
        return 0
    try:
        final = criar(Path(args.dados).resolve(), Path(args.destino).resolve(), args.manter_dias)
    except Exception as exc:
        print(f"backup falhou: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(f"backup criado: {final}")
    print(verificar(final))
    return 0


if __name__ == "__main__":
    sys.exit(main())
