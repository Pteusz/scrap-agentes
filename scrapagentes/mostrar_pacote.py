"""Ingere um vídeo no adaptador `manual` numa pasta temporária e imprime o pacote de forma legível.

Uso: python -m scrapagentes.mostrar_pacote <video> [--legenda texto] [--saida pasta]
Roda a transcrição de verdade (modelo configurado) e a seleção de frames; serve para conferir o
formato do pacote com um vídeo real. Não toca no banco de produção.
"""
import argparse
import shutil
import sys
import tempfile
from pathlib import Path

from scrapagentes import servico
from scrapagentes.banco import conectar, migrar
from scrapagentes.config import Config


def formatar(pacote: dict) -> str:
    c = pacote["contexto"]
    linhas = ["== CONTEXTO =="]
    linhas += [f"{k}: {v}" for k, v in c.items()]
    m = pacote["metricas"]
    linhas += ["", "== MÉTRICAS ==", "sem coleta" if m is None else f"coletado_em: {m['coletado_em']}"]
    if m:
        linhas += [f"{n}: {v:g}" for n, v in m["valores"].items()]
    if pacote["texto"] is not None:
        linhas += ["", "== TEXTO FALADO =="]
        linhas += [f"[{t['inicio_s']:7.2f} -> {t['fim_s']:7.2f}] {t['texto']}" for t in pacote["texto"]] or ["(sem fala)"]
    linhas += ["", "== IMAGENS =="]
    for i in pacote["imagens"]:
        if "segundo" in i:
            fala = i["fala_proxima"] or "(sem fala)"
            linhas.append(f"{i['ordem']:2d}  {i['segundo']:7.2f}s  {i['marcador']:6s}  {i['rota']}\n      fala próxima: {fala}")
        else:
            linhas.append(f"{i['ordem']:2d}  {i['rota']}")
    return "\n".join(linhas)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m scrapagentes.mostrar_pacote")
    p.add_argument("video", type=Path)
    p.add_argument("--legenda", default="")
    p.add_argument("--saida", type=Path, default=None, help="pasta de dados a manter (padrão: temporária)")
    args = p.parse_args(argv)
    dados = args.saida or Path(tempfile.mkdtemp(prefix="sa-pacote-"))
    config = Config(dados=dados)
    conn = conectar(config.banco)
    migrar(conn)
    r = servico.enfileirar_ingestao(
        conn, config, rede="manual", url=None, nicho="demonstracao", subnichos=["exemplo", "video"],
        entrada={"arquivos": [str(args.video)], "conta": "conta_exemplo", "formato": "video",
                 "data_publicacao": "2026-03-10", "legenda": args.legenda,
                 "metricas": {"curtidas": 120, "comentarios": 8}},
    )
    servico.processar_fila(conn, config)
    job = servico.obter_job(conn, r["job_id"])
    if job["estado"] != "concluido":
        print(f"ERRO: {job['erro']}", file=sys.stderr)
        return 1
    print(formatar(servico.montar_pacote(conn, job["item_id"])))
    busca = servico.buscar(conn, nicho="demonstracao", subnicho=["exemplo", "video"], formato="video",
                           metrica="curtidas", minimo=100, q="hackers")
    print("\n== BUSCA COMBINADA ==\nnicho=demonstracao subnicho=exemplo,video (todos) formato=video "
          "curtidas>=100 q=hackers")
    print(f"total={busca['total']} ids={[i['id'] for i in busca['itens']]}")
    print(f"\n(dados em {dados})")
    if args.saida is None:
        shutil.rmtree(dados, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
