"""Regras do núcleo, agnósticas de rede: ingestão, coleta, busca e pacote.

Nesta etapa a ingestão é síncrona (o worker entra na etapa 07). Cada chamada cria um job e o
deixa em `concluido` ou `erro`.
"""
import json
import logging
import re
import shutil
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from scrapagentes import adaptadores
from scrapagentes.adaptadores.base import METRICAS_PADRAO, Adaptador, ErroAdaptador
from scrapagentes.banco import agora_iso, reindexar_busca
from scrapagentes.config import Config
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

def _criar_job(conn, tipo: str, item_id: int | None, parametros: dict) -> int:
    agora = agora_iso()
    with conn:
        cur = conn.execute(
            "INSERT INTO job (item_id, tipo, estado, tentativas, parametros, criado_em, atualizado_em) "
            "VALUES (?, ?, 'executando', 1, ?, ?, ?)",
            (item_id, tipo, json.dumps(parametros, ensure_ascii=False), agora, agora),
        )
    return cur.lastrowid


def _fechar_job(conn, job_id: int, erro: str | None, item_id: int | None = None) -> None:
    with conn:
        conn.execute(
            "UPDATE job SET estado = ?, erro = ?, item_id = COALESCE(?, item_id), atualizado_em = ? "
            "WHERE id = ?",
            ("erro" if erro else "concluido", erro, item_id, agora_iso(), job_id),
        )


def obter_job(conn, job_id: int) -> dict:
    j = conn.execute("SELECT * FROM job WHERE id = ?", (job_id,)).fetchone()
    if j is None:
        raise ItemNaoEncontrado(f"job {job_id} não existe")
    d = dict(j)
    d["parametros"] = json.loads(d["parametros"]) if d["parametros"] else None
    return d


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


def _gravar_midia(conn, config: Config, item_id: int, formato: str, arquivos: list[Path]) -> Path:
    """Grava em `midia/<id>.novo` e devolve essa pasta; o chamador a renomeia após o commit."""
    pasta_rel = Path("midia") / str(item_id)
    pasta = config.dados / "midia" / f"{item_id}.novo"
    shutil.rmtree(pasta, ignore_errors=True)
    pasta.mkdir(parents=True)
    conn.execute("DELETE FROM imagem WHERE item_id = ?", (item_id,))
    if formato == "video":
        # Frames só na etapa 05; guarda o original para os próximos estágios.
        shutil.copyfile(arquivos[0], pasta / f"original{arquivos[0].suffix.lower()}")
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


def ingerir(
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
    """Cria o job, resolve pelo adaptador e grava o item. Devolve {job_id, item_id}."""
    entrada = entrada or {}
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

    job_id = _criar_job(conn, "ingestao", existente["id"] if existente else None, {
        "rede": adaptador.nome, "url": url_canonica, "nicho": nicho_norm,
        "subnichos": tags, "reprocessar": reprocessar,
    })
    midia_nova = None
    resolvido = None
    try:
        resolvido = adaptador.resolver(url_canonica, entrada)
        metricas = _validar_metricas(adaptador, resolvido.metricas)
        agora = agora_iso()
        conn.execute("BEGIN IMMEDIATE")  # trava de escrita antes de ler o MAX(coletado_em)
        with conn:
            if existente is None:
                cur = conn.execute(
                    "INSERT INTO item (rede, url, conta, nicho, formato, data_publicacao, legenda, "
                    "duracao_s, criado_em, atualizado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (adaptador.nome, url_canonica, resolvido.conta, nicho_norm, resolvido.formato,
                     resolvido.data_publicacao, resolvido.legenda, resolvido.duracao_s, agora, agora),
                )
                item_id = cur.lastrowid
                midia_nova = _gravar_midia(conn, config, item_id, resolvido.formato, resolvido.arquivos)
            else:
                item_id = existente["id"]
                conn.execute(
                    "UPDATE item SET legenda = COALESCE(?, legenda), nicho = COALESCE(?, nicho), atualizado_em = ? "
                    "WHERE id = ?",
                    (resolvido.legenda or None, nicho_norm, agora, item_id),
                )
                if reprocessar:
                    midia_nova = _gravar_midia(conn, config, item_id, resolvido.formato, resolvido.arquivos)
            if tags is not None:
                _trocar_subnichos(conn, item_id, tags)
            if metricas:
                _gravar_coleta(conn, item_id, metricas)
            reindexar_busca(conn, item_id)
        if midia_nova is not None:  # só troca a mídia depois do commit
            final = config.dados / "midia" / str(item_id)
            shutil.rmtree(final, ignore_errors=True)
            midia_nova.rename(final)
        _fechar_job(conn, job_id, None, item_id)
        return {"job_id": job_id, "item_id": item_id}
    except ErroAdaptador as exc:
        _fechar_job(conn, job_id, f"{exc.codigo}: {exc}")
    except (ErroDeUso, ValueError) as exc:
        _fechar_job(conn, job_id, f"entrada_invalida: {exc}")
    except Exception as exc:
        log.exception("falha inesperada na ingestão (job %s)", job_id)
        _fechar_job(conn, job_id, f"erro_interno: {type(exc).__name__}")
    finally:
        if resolvido is not None and resolvido.pasta_temporaria is not None:
            shutil.rmtree(resolvido.pasta_temporaria, ignore_errors=True)
    if midia_nova is not None:
        shutil.rmtree(midia_nova, ignore_errors=True)
    return {"job_id": job_id, "item_id": existente["id"] if existente else None}


def coletar(conn: sqlite3.Connection, item_id: int, entrada: dict | None = None) -> dict:
    """Coleta de métricas sob demanda: nunca sobrescreve, sempre acrescenta linhas."""
    item = conn.execute("SELECT * FROM item WHERE id = ?", (item_id,)).fetchone()
    if item is None:
        raise ItemNaoEncontrado(f"item {item_id} não existe")
    adaptador = adaptadores.obter(item["rede"])
    if adaptador is None:
        raise ErroDeUso(f"adaptador da rede {item['rede']} não está registrado")
    _validar_metricas(adaptador, (entrada or {}).get("metricas"))

    job_id = _criar_job(conn, "coleta", item_id, {"item_id": item_id})
    try:
        metricas = _validar_metricas(adaptador, adaptador.coletar_metricas(dict(item), entrada))
        if not metricas:
            raise ErroAdaptador("nenhuma métrica obtida")
        conn.execute("BEGIN IMMEDIATE")  # trava de escrita antes de ler o MAX(coletado_em)
        with conn:
            _gravar_coleta(conn, item_id, metricas)
        _fechar_job(conn, job_id, None, item_id)
    except ErroAdaptador as exc:
        _fechar_job(conn, job_id, f"{exc.codigo}: {exc}")
    except (ErroDeUso, ValueError) as exc:
        _fechar_job(conn, job_id, f"entrada_invalida: {exc}")
    except Exception as exc:
        log.exception("falha inesperada na coleta (job %s)", job_id)
        _fechar_job(conn, job_id, f"erro_interno: {type(exc).__name__}")
    return {"job_id": job_id, "item_id": item_id}


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
