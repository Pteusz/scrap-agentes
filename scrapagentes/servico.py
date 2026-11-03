"""Regras do núcleo, agnósticas de rede: fila, ingestão, coleta, busca e pacote.

A API só enfileira (`enfileirar_*`); o worker (`trabalhador.py`) reivindica e executa os jobs.
Vídeo passa por transcrição e seleção de frames antes de gravar.
"""
import json
import logging
import re
import shutil
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import tempfile

from scrapagentes import adaptadores, transcricao
from scrapagentes.adaptadores.base import METRICAS_PADRAO, Adaptador, ErroAdaptador
from scrapagentes.banco import agora_iso, reindexar_busca
from scrapagentes.config import Config
from scrapagentes.frames import selecionar_frames
from scrapagentes.tags import normalizar_tag, normalizar_tags

log = logging.getLogger("scrapagentes")


class ErroDeUso(Exception):
    """Entrada inválida do operador (vira 422 na API)."""


class ItemNaoEncontrado(Exception):
    """Item ou recurso inexistente (vira 404 na API)."""


# ---------- métricas ----------

def _validar_metricas(adaptador: Adaptador, metricas: dict) -> dict[str, float]:
    permitidas = set(METRICAS_PADRAO) | set(adaptador.metricas_suportadas)
    saida = {}
    for nome, valor in (metricas or {}).items():
        if nome not in permitidas:
            raise ErroDeUso(f"métrica desconhecida para a rede {adaptador.nome}: {nome}")
        if isinstance(valor, bool) or not isinstance(valor, (int, float)):
            raise ErroDeUso(f"valor não numérico na métrica {nome}")
        saida[nome] = float(valor)
    return saida


def _proximo_coletado_em(conn: sqlite3.Connection, item_id: int) -> str:
    """Instante da coleta; sempre posterior à última do item, para que coletas não se misturem."""
    agora = agora_iso()
    ultima = conn.execute(
        "SELECT MAX(coletado_em) FROM metrica WHERE item_id = ?", (item_id,)
    ).fetchone()[0]
    if ultima and agora <= ultima:
        agora = (datetime.fromisoformat(ultima) + timedelta(microseconds=1)).isoformat(
            timespec="microseconds"
        )
    return agora


def _gravar_coleta(conn: sqlite3.Connection, item_id: int, metricas: dict[str, float]) -> str:
    """Métrica nunca sobrescreve: cada coleta insere linhas novas."""
    coletado_em = _proximo_coletado_em(conn, item_id)
    conn.executemany(
        "INSERT INTO metrica (item_id, coletado_em, nome, valor) VALUES (?, ?, ?, ?)",
        [(item_id, coletado_em, n, v) for n, v in metricas.items()],
    )
    return coletado_em


def _metricas_recentes(conn: sqlite3.Connection, item_id: int) -> dict | None:
    ultima = conn.execute(
        "SELECT MAX(coletado_em) FROM metrica WHERE item_id = ?", (item_id,)
    ).fetchone()[0]
    if ultima is None:
        return None
    linhas = conn.execute(
        "SELECT nome, valor FROM metrica WHERE item_id = ? AND coletado_em = ? ORDER BY nome",
        (item_id, ultima),
    ).fetchall()
    return {"coletado_em": ultima, "valores": {r["nome"]: r["valor"] for r in linhas}}


# ---------- jobs ----------

MAX_TENTATIVAS = 3  # a primeira execução mais no máximo 2 retentativas
# Erros que repetir não resolve: o job vai direto para `erro`.
CODIGOS_DEFINITIVOS = {"nao_encontrado", "formato_nao_suportado", "exige_login", "entrada_invalida"}


class Queda(BaseException):
    """Simula a morte do processo no meio de um job (só testes). Não é capturada pelo worker."""


def _criar_job(conn, tipo: str, item_id: int | None, parametros: dict) -> int:
    agora = agora_iso()
    with conn:
        cur = conn.execute(
            "INSERT INTO job (item_id, tipo, estado, tentativas, parametros, criado_em, atualizado_em) "
            "VALUES (?, ?, 'pendente', 0, ?, ?, ?)",
            (item_id, tipo, json.dumps(parametros, ensure_ascii=False), agora, agora),
        )
    return cur.lastrowid


def obter_job(conn, job_id: int) -> dict:
    j = conn.execute("SELECT * FROM job WHERE id = ?", (job_id,)).fetchone()
    if j is None:
        raise ItemNaoEncontrado(f"job {job_id} não existe")
    d = dict(j)
    d["parametros"] = json.loads(d["parametros"]) if d["parametros"] else None
    return d


def reivindicar_job(conn) -> dict | None:
    """Pega o job pendente mais antigo e o marca `executando`. Atômico entre processos."""
    with conn:
        linha = conn.execute(
            "UPDATE job SET estado = 'executando', tentativas = tentativas + 1, atualizado_em = ? "
            "WHERE id = (SELECT id FROM job WHERE estado = 'pendente' ORDER BY atualizado_em, id LIMIT 1) "
            "RETURNING id",
            (agora_iso(),),
        ).fetchone()
    return obter_job(conn, linha["id"]) if linha else None


def _pasta_entrada(config: Config, job_id: int) -> Path:
    return config.dados / "entrada" / str(job_id)


def _limpar_entrada(config: Config, job_id: int) -> None:
    shutil.rmtree(_pasta_entrada(config, job_id), ignore_errors=True)


def _registrar_falha(conn, config: Config, job: dict, codigo: str, mensagem: str) -> None:
    """Falha transitória volta a `pendente` (no fim da fila) até esgotar as tentativas."""
    tentativas = job["tentativas"]
    linha = f"tentativa {tentativas}/{MAX_TENTATIVAS}: {codigo}: {mensagem}"
    definitivo = codigo in CODIGOS_DEFINITIVOS or tentativas >= MAX_TENTATIVAS
    if definitivo and tentativas == 1:
        texto = f"{codigo}: {mensagem}"
    else:
        texto = "\n".join(filter(None, [job.get("erro"), linha]))
    with conn:
        conn.execute(
            "UPDATE job SET estado = ?, erro = ?, atualizado_em = ? WHERE id = ?",
            ("erro" if definitivo else "pendente", texto, agora_iso(), job["id"]),
        )
    if definitivo:
        _limpar_entrada(config, job["id"])


def recuperar(conn, config: Config) -> dict:
    """Ao subir o worker: jobs que ficaram `executando` voltam a `pendente`; limpa sobras.

    Sem duplicar nada: o item, as imagens, as métricas e o fechamento do job são gravados numa só
    transação, então um job interrompido ou foi gravado por inteiro ou não gravou nada.
    """
    voltaram = esgotados = 0
    for j in conn.execute("SELECT id, tentativas, erro FROM job WHERE estado = 'executando'").fetchall():
        nota = f"tentativa {j['tentativas']}/{MAX_TENTATIVAS}: processo interrompido"
        texto = "\n".join(filter(None, [j["erro"], nota]))
        esgotou = j["tentativas"] >= MAX_TENTATIVAS
        with conn:
            conn.execute(
                "UPDATE job SET estado = ?, erro = ?, atualizado_em = ? WHERE id = ?",
                ("erro" if esgotou else "pendente", texto, agora_iso(), j["id"]),
            )
        if esgotou:
            _limpar_entrada(config, j["id"])
            esgotados += 1
        else:
            voltaram += 1
    for pasta in config.dados.glob("processamento-*"):
        shutil.rmtree(pasta, ignore_errors=True)
    _varrer_midia_nova(conn, config)
    return {"voltaram": voltaram, "esgotados": esgotados}


def _varrer_midia_nova(conn, config: Config) -> None:
    """`midia/<id>.novo` sobrou de uma queda. Se o commit do item aconteceu (job fechado depois da
    pasta ser escrita), conclui a troca; senão, descarta."""
    if not config.midia.is_dir():
        return
    for pasta in config.midia.glob("*.novo"):
        try:
            item_id = int(pasta.name.removesuffix(".novo"))
        except ValueError:
            continue
        gravado_em = datetime.fromtimestamp(pasta.stat().st_mtime, tz=timezone.utc).isoformat(timespec="microseconds")
        commit = conn.execute(
            "SELECT 1 FROM job WHERE item_id = ? AND tipo = 'ingestao' AND estado = 'concluido' "
            "AND atualizado_em >= ?", (item_id, gravado_em),
        ).fetchone()
        if commit:
            _trocar_midia(pasta, config.midia / str(item_id))
        else:
            shutil.rmtree(pasta, ignore_errors=True)


def _trocar_midia(nova: Path, final: Path) -> None:
    shutil.rmtree(final, ignore_errors=True)
    nova.rename(final)


# ---------- ingestão ----------

def _escolher_adaptador(rede: str | None, url: str) -> Adaptador:
    if rede:
        adaptador = adaptadores.obter(rede)
        if adaptador is None:
            raise ErroDeUso(f"rede desconhecida: {rede}. Disponíveis: {', '.join(adaptadores.nomes())}")
        return adaptador
    adaptador = adaptadores.detectar(url)
    if adaptador is None:
        raise ErroDeUso("não foi possível reconhecer a rede pela url; informe `rede`")
    return adaptador


transcrever_video = transcricao.transcrever  # ponto de troca para os testes sem modelo


def _processar_video(config: Config, arquivo: Path, duracao_s: float, pasta: Path) -> dict:
    """Transcrição e frames. Trabalho pesado: roda antes de abrir a transação de escrita."""
    try:
        trechos = transcrever_video(arquivo, ffmpeg=config.ffmpeg)
    except transcricao.ErroTranscricao as exc:  # ex.: vídeo sem faixa de áudio
        log.warning("vídeo sem transcrição: %s", exc)
        trechos = []
    frames = selecionar_frames(arquivo, pasta, duracao_s, ffmpeg=config.ffmpeg)
    return {"trechos": trechos, "frames": frames}


def _gravar_midia(conn, config: Config, item_id: int, formato: str, arquivos: list[Path],
                  processado: dict | None = None) -> Path:
    """Grava em `midia/<id>.novo` e devolve essa pasta; o chamador a renomeia após o commit."""
    pasta_rel = Path("midia") / str(item_id)
    pasta = config.dados / "midia" / f"{item_id}.novo"
    shutil.rmtree(pasta, ignore_errors=True)
    pasta.mkdir(parents=True)
    conn.execute("DELETE FROM imagem WHERE item_id = ?", (item_id,))
    if formato == "video":
        shutil.copyfile(arquivos[0], pasta / f"original{arquivos[0].suffix.lower()}")
        conn.execute(
            "UPDATE item SET texto = ? WHERE id = ?",
            (json.dumps(processado["trechos"], ensure_ascii=False), item_id),
        )
        for f in processado["frames"]:
            destino = pasta / f"{f['ordem']:03d}.jpg"
            shutil.copyfile(f["arquivo"], destino)
            conn.execute(
                "INSERT INTO imagem (item_id, ordem, arquivo, segundo, marcador) VALUES (?, ?, ?, ?, ?)",
                (item_id, f["ordem"], (pasta_rel / destino.name).as_posix(), f["segundo"], f["marcador"]),
            )
        return pasta
    for ordem, origem in enumerate(arquivos, start=1):
        destino = pasta / f"{ordem:03d}{origem.suffix.lower()}"
        shutil.copyfile(origem, destino)
        conn.execute(
            "INSERT INTO imagem (item_id, ordem, arquivo) VALUES (?, ?, ?)",
            (item_id, ordem, (pasta_rel / destino.name).as_posix()),
        )
    return pasta


def _trocar_subnichos(conn, item_id: int, tags: list[str]) -> None:
    conn.execute("DELETE FROM subnicho WHERE item_id = ?", (item_id,))
    conn.executemany(
        "INSERT INTO subnicho (item_id, tag) VALUES (?, ?)", [(item_id, t) for t in tags]
    )


def enfileirar_ingestao(
    conn: sqlite3.Connection,
    config: Config,
    *,
    rede: str | None,
    url: str | None,
    nicho: str | None,
    subnichos: list[str] | None,
    entrada: dict | None = None,
    reprocessar: bool = False,
) -> dict:
    """Valida a request e cria o job `pendente`. Devolve {job_id, item_id}.

    `item_id` é o do item já existente para a mesma rede+url; num item novo é `None` até o worker
    criá-lo (consulte `GET /jobs/{id}`).
    """
    entrada = dict(entrada or {})
    for nome, valor in (("rede", rede), ("url", url), ("nicho", nicho)):
        if valor is not None and not isinstance(valor, str):
            raise ErroDeUso(f"`{nome}` deve ser texto")
    if subnichos is not None and (
        not isinstance(subnichos, list) or not all(isinstance(t, str) for t in subnichos)
    ):
        raise ErroDeUso("`subnichos` deve ser uma lista de textos")
    try:
        adaptador = _escolher_adaptador(rede, url or "")
        url_canonica = adaptador.canonizar_url(url or "", entrada)
    except ValueError as exc:
        raise ErroDeUso(str(exc)) from exc
    _validar_metricas(adaptador, entrada.get("metricas"))
    tags = normalizar_tags(subnichos) if subnichos is not None else None
    nicho_norm = normalizar_tag(nicho) if nicho else None

    existente = conn.execute(
        "SELECT id FROM item WHERE rede = ? AND url = ?", (adaptador.nome, url_canonica)
    ).fetchone()
    if existente is None and not nicho_norm:
        raise ErroDeUso("`nicho` é obrigatório ao criar um item")

    arquivos = [Path(a) for a in entrada.pop("arquivos", None) or []]
    entrada["arquivos"] = []
    parametros = {
        "rede": adaptador.nome, "url": url_canonica, "nicho": nicho_norm,
        "subnichos": tags, "reprocessar": reprocessar, "entrada": entrada,
    }
    job_id = _criar_job(conn, "ingestao", existente["id"] if existente else None, parametros)
    if arquivos:  # o upload mora em dados/entrada/<job> até o job terminar
        try:
            pasta = _pasta_entrada(config, job_id)
            pasta.mkdir(parents=True)
            for a in arquivos:
                shutil.copyfile(a, pasta / a.name)
            entrada["arquivos"] = [a.name for a in arquivos]
            with conn:
                conn.execute(
                    "UPDATE job SET parametros = ? WHERE id = ?",
                    (json.dumps(parametros, ensure_ascii=False), job_id),
                )
        except Exception:
            _limpar_entrada(config, job_id)
            with conn:
                conn.execute("DELETE FROM job WHERE id = ?", (job_id,))
            raise
    return {"job_id": job_id, "item_id": existente["id"] if existente else None}


def enfileirar_coleta(conn: sqlite3.Connection, item_id: int, entrada: dict | None = None) -> dict:
    """Coleta de métricas sob demanda: cria o job `pendente`."""
    item = conn.execute("SELECT rede FROM item WHERE id = ?", (item_id,)).fetchone()
    if item is None:
        raise ItemNaoEncontrado(f"item {item_id} não existe")
    adaptador = adaptadores.obter(item["rede"])
    if adaptador is None:
        raise ErroDeUso(f"adaptador da rede {item['rede']} não está registrado")
    entrada = entrada or {}
    _validar_metricas(adaptador, entrada.get("metricas"))
    job_id = _criar_job(conn, "coleta", item_id, {"item_id": item_id, "entrada": entrada})
    return {"job_id": job_id, "item_id": item_id}


def executar_job(conn: sqlite3.Connection, config: Config, job: dict) -> None:
    """Executa um job já reivindicado. Falhas viram retentativa ou `erro`; nunca propaga Exception."""
    try:
        if job["tipo"] == "ingestao":
            _executar_ingestao(conn, config, job)
        else:
            _executar_coleta(conn, job)
    except ErroAdaptador as exc:
        _registrar_falha(conn, config, job, exc.codigo, str(exc))
    except (ErroDeUso, ValueError) as exc:
        _registrar_falha(conn, config, job, "entrada_invalida", str(exc))
    except Exception as exc:
        log.exception("falha inesperada no job %s", job["id"])
        _registrar_falha(conn, config, job, "erro_interno", type(exc).__name__)
    else:
        if job["tipo"] == "ingestao":
            _limpar_entrada(config, job["id"])


def _executar_ingestao(conn, config: Config, job: dict) -> None:
    p = job["parametros"]
    entrada = dict(p["entrada"])
    entrada["arquivos"] = [_pasta_entrada(config, job["id"]) / n for n in entrada.get("arquivos", [])]
    adaptador = adaptadores.obter(p["rede"])
    if adaptador is None:
        raise ErroDeUso(f"adaptador da rede {p['rede']} não está registrado")
    url, tags, nicho, reprocessar = p["url"], p["subnichos"], p["nicho"], p["reprocessar"]
    existente = conn.execute(
        "SELECT id FROM item WHERE rede = ? AND url = ?", (adaptador.nome, url)
    ).fetchone()
    if existente is None and not nicho:
        raise ErroDeUso("`nicho` é obrigatório ao criar um item")

    midia_nova = None
    resolvido = None
    pasta_proc = None
    try:
        resolvido = adaptador.resolver(url, entrada)
        metricas = _validar_metricas(adaptador, resolvido.metricas)
        processado = None
        # Item que perdeu a mídia (queda no meio da troca) também é refeito.
        sem_midia = existente is not None and not (config.midia / str(existente["id"])).is_dir()
        refazer = existente is None or reprocessar or sem_midia
        if resolvido.formato == "video" and refazer:
            config.dados.mkdir(parents=True, exist_ok=True)
            pasta_proc = Path(tempfile.mkdtemp(prefix="processamento-", dir=config.dados))
            processado = _processar_video(config, resolvido.arquivos[0], resolvido.duracao_s, pasta_proc)
        agora = agora_iso()
        conn.execute("BEGIN IMMEDIATE")  # trava de escrita antes de ler o MAX(coletado_em)
        with conn:
            if existente is None:
                cur = conn.execute(
                    "INSERT INTO item (rede, url, conta, nicho, formato, data_publicacao, legenda, "
                    "duracao_s, criado_em, atualizado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (adaptador.nome, url, resolvido.conta, nicho, resolvido.formato,
                     resolvido.data_publicacao, resolvido.legenda, resolvido.duracao_s, agora, agora),
                )
                item_id = cur.lastrowid
            else:
                item_id = existente["id"]
                conn.execute(
                    "UPDATE item SET legenda = COALESCE(?, legenda), nicho = COALESCE(?, nicho), atualizado_em = ? "
                    "WHERE id = ?",
                    (resolvido.legenda or None, nicho, agora, item_id),
                )
            if refazer:
                midia_nova = _gravar_midia(conn, config, item_id, resolvido.formato, resolvido.arquivos, processado)
            if tags is not None:
                _trocar_subnichos(conn, item_id, tags)
            if metricas:
                _gravar_coleta(conn, item_id, metricas)
            reindexar_busca(conn, item_id)
            conn.execute(  # o job fecha na mesma transação que grava o item
                "UPDATE job SET estado = 'concluido', item_id = ?, atualizado_em = ? WHERE id = ?",
                (item_id, agora_iso(), job["id"]),
            )
        if midia_nova is not None:  # só troca a mídia depois do commit
            nova, midia_nova = midia_nova, None
            _trocar_midia(nova, config.dados / "midia" / str(item_id))
    finally:
        if resolvido is not None and resolvido.pasta_temporaria is not None:
            shutil.rmtree(resolvido.pasta_temporaria, ignore_errors=True)
        if pasta_proc is not None:
            shutil.rmtree(pasta_proc, ignore_errors=True)
        if midia_nova is not None:  # falha antes do commit
            shutil.rmtree(midia_nova, ignore_errors=True)


def _executar_coleta(conn, job: dict) -> None:
    item_id = job["parametros"]["item_id"]
    entrada = job["parametros"].get("entrada") or {}
    item = conn.execute("SELECT * FROM item WHERE id = ?", (item_id,)).fetchone()
    if item is None:
        raise ErroDeUso(f"item {item_id} não existe")
    adaptador = adaptadores.obter(item["rede"])
    if adaptador is None:
        raise ErroDeUso(f"adaptador da rede {item['rede']} não está registrado")
    metricas = _validar_metricas(adaptador, adaptador.coletar_metricas(dict(item), entrada))
    if not metricas:
        raise ErroAdaptador("nenhuma métrica obtida")
    conn.execute("BEGIN IMMEDIATE")  # trava de escrita antes de ler o MAX(coletado_em)
    with conn:
        _gravar_coleta(conn, item_id, metricas)
        conn.execute(
            "UPDATE job SET estado = 'concluido', item_id = ?, atualizado_em = ? WHERE id = ?",
            (item_id, agora_iso(), job["id"]),
        )


def processar_fila(conn, config: Config, limite: int | None = None) -> int:
    """Executa jobs pendentes em série até esvaziar a fila. Devolve quantos rodou."""
    rodou = 0
    while limite is None or rodou < limite:
        job = reivindicar_job(conn)
        if job is None:
            break
        executar_job(conn, config, job)
        rodou += 1
    return rodou


# ---------- subnichos ----------

def atualizar_subnichos(conn, item_id: int, adicionar=None, remover=None, substituir=None) -> list[str]:
    if conn.execute("SELECT 1 FROM item WHERE id = ?", (item_id,)).fetchone() is None:
        raise ItemNaoEncontrado(f"item {item_id} não existe")
    if substituir is not None and (adicionar or remover):
        raise ErroDeUso("`substituir` não pode ser combinado com `adicionar` ou `remover`")
    with conn:
        if substituir is not None:
            _trocar_subnichos(conn, item_id, normalizar_tags(substituir))
        else:
            for tag in normalizar_tags(adicionar):
                conn.execute(
                    "INSERT OR IGNORE INTO subnicho (item_id, tag) VALUES (?, ?)", (item_id, tag)
                )
            for tag in normalizar_tags(remover):
                conn.execute("DELETE FROM subnicho WHERE item_id = ? AND tag = ?", (item_id, tag))
    return _tags(conn, item_id)


def _tags(conn, item_id: int) -> list[str]:
    return [r["tag"] for r in conn.execute(
        "SELECT tag FROM subnicho WHERE item_id = ? ORDER BY tag", (item_id,))]


# ---------- busca ----------

def _consulta_fts(q: str) -> str:
    termos = re.findall(r"\w+", q)
    if not termos:
        raise ErroDeUso("`q` não tem nenhuma palavra pesquisável")
    return " ".join('"' + t.replace('"', '""') + '"' for t in termos)


def _resumo(conn, linha: sqlite3.Row) -> dict:
    d = dict(linha)
    d.pop("texto", None)
    d["subnichos"] = _tags(conn, d["id"])
    d["metricas"] = _metricas_recentes(conn, d["id"])
    return d


def buscar(
    conn: sqlite3.Connection,
    *,
    rede=None, conta=None, nicho=None, subnicho=None, modo_subnicho="todos",
    formato=None, publicado_de=None, publicado_ate=None,
    metrica=None, minimo=None, maximo=None, q=None,
    pagina=1, tamanho=20,
) -> dict:
    cond, par = [], []
    for coluna, valor in (("rede", rede), ("conta", conta), ("formato", formato)):
        if valor:
            cond.append(f"i.{coluna} = ?")
            par.append(valor)
    if nicho:
        cond.append("i.nicho = ?")
        par.append(normalizar_tag(nicho))
    tags = normalizar_tags(subnicho)
    if tags:
        marcas = ",".join("?" * len(tags))
        if modo_subnicho == "qualquer":
            cond.append(f"EXISTS (SELECT 1 FROM subnicho s WHERE s.item_id = i.id AND s.tag IN ({marcas}))")
            par += tags
        elif modo_subnicho == "todos":
            cond.append(
                f"i.id IN (SELECT item_id FROM subnicho WHERE tag IN ({marcas}) "
                "GROUP BY item_id HAVING COUNT(DISTINCT tag) = ?)"
            )
            par += tags + [len(tags)]
        else:
            raise ErroDeUso("`modo_subnicho` deve ser `todos` ou `qualquer`")
    try:
        if publicado_de:
            datetime.fromisoformat(publicado_de)
            cond.append("date(i.data_publicacao) >= date(?)")
            par.append(publicado_de)
        if publicado_ate:
            datetime.fromisoformat(publicado_ate)
            cond.append("date(i.data_publicacao) <= date(?)")
            par.append(publicado_ate)
    except ValueError as exc:
        raise ErroDeUso("datas devem estar em ISO 8601 (AAAA-MM-DD)") from exc
    if (minimo is not None or maximo is not None) and not metrica:
        raise ErroDeUso("`min` e `max` exigem o nome da `metrica`")
    if metrica:
        valor = (
            "(SELECT m.valor FROM metrica m WHERE m.item_id = i.id AND m.nome = ? AND m.coletado_em = "
            "(SELECT MAX(coletado_em) FROM metrica WHERE item_id = i.id))"
        )
        cond.append(f"{valor} IS NOT NULL")
        par.append(metrica)
        if minimo is not None:
            cond.append(f"{valor} >= ?")
            par += [metrica, minimo]
        if maximo is not None:
            cond.append(f"{valor} <= ?")
            par += [metrica, maximo]
    if q:
        cond.append("i.id IN (SELECT rowid FROM busca WHERE busca MATCH ?)")
        par.append(_consulta_fts(q))

    onde = ("WHERE " + " AND ".join(cond)) if cond else ""
    total = conn.execute(f"SELECT COUNT(*) FROM item i {onde}", par).fetchone()[0]
    linhas = conn.execute(
        f"SELECT i.* FROM item i {onde} ORDER BY i.id DESC LIMIT ? OFFSET ?",
        par + [tamanho, (pagina - 1) * tamanho],
    ).fetchall()
    return {
        "total": total, "pagina": pagina, "tamanho": tamanho,
        "itens": [_resumo(conn, l) for l in linhas],
    }


# ---------- pacote ----------

def _fala_proxima(segmentos: list[dict], t: float) -> str | None:
    """Trecho de fala que contém o segundo t, ou o mais próximo dele."""
    if not segmentos:
        return None

    def distancia(s):
        if s["inicio_s"] <= t < s["fim_s"]:
            return 0.0
        return min(abs(t - s["inicio_s"]), abs(t - s["fim_s"]))

    return min(segmentos, key=distancia)["texto"]


def montar_pacote(conn: sqlite3.Connection, item_id: int) -> dict:
    item = conn.execute("SELECT * FROM item WHERE id = ?", (item_id,)).fetchone()
    if item is None:
        raise ItemNaoEncontrado(f"item {item_id} não existe")
    video = item["formato"] == "video"
    segmentos = json.loads(item["texto"]) if item["texto"] else []
    imagens = []
    for im in conn.execute("SELECT * FROM imagem WHERE item_id = ? ORDER BY ordem", (item_id,)):
        d = {"ordem": im["ordem"], "rota": f"/itens/{item_id}/imagens/{im['ordem']}"}
        if video:
            d["segundo"] = im["segundo"]
            d["marcador"] = im["marcador"]
            d["fala_proxima"] = (
                _fala_proxima(segmentos, im["segundo"]) if im["segundo"] is not None else None
            )
        imagens.append(d)
    return {
        "contexto": {
            "rede": item["rede"], "link": item["url"], "conta": item["conta"],
            "nicho": item["nicho"], "subnichos": _tags(conn, item_id), "formato": item["formato"],
            "data_publicacao": item["data_publicacao"], "legenda": item["legenda"],
            "duracao_s": item["duracao_s"],
        },
        "metricas": _metricas_recentes(conn, item_id),
        "texto": segmentos if video else None,
        "imagens": imagens,
    }


def caminho_imagem(conn, config: Config, item_id: int, ordem: int) -> Path:
    im = conn.execute(
        "SELECT arquivo FROM imagem WHERE item_id = ? AND ordem = ?", (item_id, ordem)
    ).fetchone()
    if im is None:
        raise ItemNaoEncontrado("imagem não encontrada")
    caminho = (config.dados / im["arquivo"]).resolve()
    if config.midia.resolve() not in caminho.parents or not caminho.is_file():
        raise ItemNaoEncontrado("arquivo da imagem não encontrado")
    return caminho
