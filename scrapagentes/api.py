"""API HTTP (SPEC, seção 7). Autenticação por chave em cabeçalho; só `/saude` é livre."""
import hmac
import shutil
import tempfile
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse

from scrapagentes import banco, servico
from scrapagentes.config import Config

CAMPOS_METRICA = ("curtidas", "comentarios", "visualizacoes", "compartilhamentos", "seguidores_conta")


def criar_app(config: Config) -> FastAPI:
    app = FastAPI(
        title="scrapagentes",
        docs_url="/docs" if config.docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if config.docs else None,
    )
    config.dados.mkdir(parents=True, exist_ok=True)
    conn_migracao = banco.conectar(config.banco)
    banco.migrar(conn_migracao)
    conn_migracao.close()

    def exigir_chave(x_api_key: str | None = Header(default=None)):
        esperada = config.chave_api
        if not esperada or not x_api_key or not hmac.compare_digest(x_api_key.encode(), esperada.encode()):
            raise HTTPException(status_code=401, detail="chave de API ausente ou inválida")

    def conexao():
        conn = banco.conectar(config.banco)
        try:
            yield conn
        finally:
            conn.close()

    @app.exception_handler(servico.ErroDeUso)
    async def _erro_de_uso(_, exc):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(servico.ItemNaoEncontrado)
    async def _nao_encontrado(_, exc):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.get("/saude")
    def saude():
        return {"status": "ok"}

    protegidas = [Depends(exigir_chave)]

    @app.post("/itens", status_code=202, dependencies=protegidas)
    async def criar_item(request: Request, conn=Depends(conexao)):
        tipo = request.headers.get("content-type", "")
        pasta_tmp = Path(tempfile.mkdtemp(prefix="scrapagentes-"))
        try:
            if tipo.startswith("application/json"):
                corpo = await request.json()
                if not isinstance(corpo, dict):
                    raise servico.ErroDeUso("o corpo JSON deve ser um objeto")
                arquivos = []
            elif tipo.startswith(("multipart/form-data", "application/x-www-form-urlencoded")):
                form = await request.form()
                corpo = {k: form.get(k) for k in form.keys() if k not in ("arquivos", "subnichos")}
                corpo["subnichos"] = form.getlist("subnichos") or None
                corpo["metricas"] = {c: form[c] for c in CAMPOS_METRICA if form.get(c) not in (None, "")}
                arquivos = []
                for i, f in enumerate(form.getlist("arquivos")):
                    if not hasattr(f, "read"):
                        raise servico.ErroDeUso("`arquivos` deve conter arquivos")
                    destino = pasta_tmp / f"{i:03d}{Path(f.filename or '').suffix.lower()}"
                    destino.write_bytes(await f.read())
                    arquivos.append(destino)
            else:
                raise servico.ErroDeUso("use application/json ou multipart/form-data")

            metricas = corpo.get("metricas") or {}
            try:
                metricas = {k: float(v) for k, v in metricas.items()}
            except (TypeError, ValueError, AttributeError):
                raise servico.ErroDeUso("métricas devem ser numéricas")
            reprocessar = str(corpo.get("reprocessar", "")).lower() in ("1", "true", "sim")
            entrada = {
                "conta": corpo.get("conta"), "formato": corpo.get("formato"),
                "data_publicacao": corpo.get("data_publicacao"), "legenda": corpo.get("legenda"),
                "duracao_s": corpo.get("duracao_s"), "metricas": metricas, "arquivos": arquivos,
            }
            return await run_in_threadpool(
                servico.ingerir, conn, config,
                rede=corpo.get("rede"), url=corpo.get("url"), nicho=corpo.get("nicho"),
                subnichos=corpo.get("subnichos"), entrada=entrada, reprocessar=reprocessar,
            )
        finally:
            shutil.rmtree(pasta_tmp, ignore_errors=True)

    @app.get("/jobs/{job_id}", dependencies=protegidas)
    def ver_job(job_id: int, conn=Depends(conexao)):
        return servico.obter_job(conn, job_id)

    @app.get("/itens/{item_id}/pacote", dependencies=protegidas)
    def pacote(item_id: int, conn=Depends(conexao)):
        return servico.montar_pacote(conn, item_id)

    @app.get("/itens/{item_id}/imagens/{ordem}", dependencies=protegidas)
    def imagem(item_id: int, ordem: int, conn=Depends(conexao)):
        return FileResponse(servico.caminho_imagem(conn, config, item_id, ordem))

    @app.get("/itens", dependencies=protegidas)
    def listar(
        rede: str | None = None,
        conta: str | None = None,
        nicho: str | None = None,
        subnicho: list[str] | None = Query(default=None),
        modo_subnicho: Literal["todos", "qualquer"] = "todos",
        formato: str | None = None,
        publicado_de: str | None = None,
        publicado_ate: str | None = None,
        metrica: str | None = None,
        minimo: float | None = Query(default=None, alias="min"),
        maximo: float | None = Query(default=None, alias="max"),
        q: str | None = None,
        pagina: int = Query(default=1, ge=1),
        tamanho: int = Query(default=20, ge=1, le=100),
        conn=Depends(conexao),
    ):
        return servico.buscar(
            conn, rede=rede, conta=conta, nicho=nicho, subnicho=subnicho,
            modo_subnicho=modo_subnicho, formato=formato, publicado_de=publicado_de,
            publicado_ate=publicado_ate, metrica=metrica, minimo=minimo, maximo=maximo,
            q=q, pagina=pagina, tamanho=tamanho,
        )

    @app.patch("/itens/{item_id}/subnichos", dependencies=protegidas)
    def alterar_subnichos(item_id: int, corpo: dict, conn=Depends(conexao)):
        desconhecidas = set(corpo) - {"adicionar", "remover", "substituir"}
        if desconhecidas:
            raise servico.ErroDeUso(f"campos desconhecidos: {', '.join(sorted(desconhecidas))}")
        tags = servico.atualizar_subnichos(
            conn, item_id, corpo.get("adicionar"), corpo.get("remover"), corpo.get("substituir")
        )
        return {"item_id": item_id, "subnichos": tags}

    @app.post("/itens/{item_id}/coletas", status_code=202, dependencies=protegidas)
    async def coletar(item_id: int, request: Request, conn=Depends(conexao)):
        corpo = {}
        if (await request.body()).strip():
            corpo = await request.json()
            if not isinstance(corpo, dict):
                raise servico.ErroDeUso("o corpo JSON deve ser um objeto")
        return await run_in_threadpool(servico.coletar, conn, item_id, corpo)

    return app


def criar_app_do_ambiente() -> FastAPI:
    return criar_app(Config.do_ambiente())
