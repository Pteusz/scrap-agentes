"""Worker: consome a tabela `job`, um job por vez (a fila é o próprio banco, sem Redis).

Ao subir, devolve a `pendente` os jobs que ficaram `executando` por uma queda anterior.
Uso: python -m scrapagentes.trabalhador [--uma-vez]
"""
import argparse
import logging
import signal
import sys
import threading
import time

from scrapagentes import banco, servico
from scrapagentes.config import Config

log = logging.getLogger("scrapagentes.trabalhador")

INTERVALO_S = 2.0


def rodar(config: Config, *, uma_vez: bool = False, parar: threading.Event | None = None,
          intervalo_s: float = INTERVALO_S) -> int:
    """Laço principal. Com `uma_vez`, esvazia a fila e sai. Devolve quantos jobs executou."""
    parar = parar or threading.Event()
    config.dados.mkdir(parents=True, exist_ok=True)
    conn = banco.conectar(config.banco)
    try:
        banco.migrar(conn)
        r = servico.recuperar(conn, config)
        if r["voltaram"] or r["esgotados"]:
            log.warning("recuperação: %d job(s) voltaram à fila, %d esgotaram as tentativas",
                        r["voltaram"], r["esgotados"])
        total = 0
        while not parar.is_set():
            job = servico.reivindicar_job(conn)
            if job is None:
                if uma_vez:
                    break
                parar.wait(intervalo_s)
                continue
            inicio = time.monotonic()
            servico.executar_job(conn, config, job)
            estado = servico.obter_job(conn, job["id"])["estado"]
            log.info("job %d (%s) tentativa %d -> %s em %.1fs", job["id"], job["tipo"],
                     job["tentativas"], estado, time.monotonic() - inicio)
            total += 1
        return total
    finally:
        conn.close()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m scrapagentes.trabalhador")
    p.add_argument("--uma-vez", action="store_true", help="esvazia a fila e sai")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parar = threading.Event()
    for sinal in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sinal, lambda *_: parar.set())  # termina o job em curso e sai
    rodar(Config.do_ambiente(), uma_vez=args.uma_vez, parar=parar)
    return 0


if __name__ == "__main__":
    sys.exit(main())
