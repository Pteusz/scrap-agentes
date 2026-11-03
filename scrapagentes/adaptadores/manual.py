"""Adaptador `manual`: aceita arquivos enviados na request (vídeo, foto ou carrossel).

Conta, formato e data de publicação vêm da request. Métricas podem ser informadas ou faltar.
"""
import hashlib
from datetime import datetime
from pathlib import Path

from scrapagentes import midia
from scrapagentes.adaptadores.base import (
    METRICAS_PADRAO, Adaptador, FormatoNaoSuportado, NaoEncontrado, Resolvido,
)

EXT_VIDEO = {".mp4", ".mov", ".mkv", ".webm"}
EXT_IMAGEM = {".jpg", ".jpeg", ".png", ".webp"}


def _metricas_informadas(entrada: dict) -> dict[str, float]:
    return {str(k): float(v) for k, v in (entrada.get("metricas") or {}).items()}


class AdaptadorManual(Adaptador):
    nome = "manual"
    formatos = ("video", "foto", "carrossel")
    metricas_suportadas = METRICAS_PADRAO

    def reconhece(self, url: str) -> bool:
        return url.startswith("manual:")

    def canonizar_url(self, url: str, entrada: dict | None = None) -> str:
        url = (url or "").strip()
        if url:
            return url
        arquivos = (entrada or {}).get("arquivos") or []
        if not arquivos:
            raise ValueError("informe a url ou envie ao menos um arquivo")
        h = hashlib.sha256()
        for a in arquivos:
            h.update(hashlib.sha256(Path(a).read_bytes()).digest())
        return "manual:" + h.hexdigest()[:16]

    def resolver(self, url: str, entrada: dict | None = None) -> Resolvido:
        entrada = entrada or {}
        for campo in ("conta", "formato", "data_publicacao"):
            if not entrada.get(campo):
                raise ValueError(f"campo obrigatório no adaptador manual: {campo}")
        formato = entrada["formato"]
        if formato not in self.formatos:
            raise FormatoNaoSuportado(f"formato fora do vocabulário: {formato}")
        datetime.fromisoformat(str(entrada["data_publicacao"]))

        arquivos = [Path(a) for a in entrada.get("arquivos") or []]
        if not arquivos:
            raise NaoEncontrado("nenhum arquivo enviado")
        for a in arquivos:
            if not a.is_file() or a.stat().st_size == 0:
                raise NaoEncontrado(f"arquivo ausente ou vazio: {a.name}")
        exts = [a.suffix.lower() for a in arquivos]
        if formato == "video":
            if len(arquivos) != 1 or exts[0] not in EXT_VIDEO:
                raise FormatoNaoSuportado("vídeo exige exatamente um arquivo de vídeo")
        elif formato == "foto":
            if len(arquivos) != 1 or exts[0] not in EXT_IMAGEM:
                raise FormatoNaoSuportado("foto exige exatamente uma imagem")
        else:
            if len(arquivos) < 2 or any(e not in EXT_IMAGEM for e in exts):
                raise FormatoNaoSuportado("carrossel exige duas ou mais imagens")

        duracao = None
        if formato == "video":
            duracao = entrada.get("duracao_s")
            duracao = float(duracao) if duracao else midia.duracao_video(arquivos[0])
            if not duracao:
                raise ValueError("não foi possível obter a duração; informe duracao_s")

        return Resolvido(
            conta=str(entrada["conta"]),
            formato=formato,
            data_publicacao=str(entrada["data_publicacao"]),
            legenda=str(entrada.get("legenda") or ""),
            duracao_s=duracao,
            arquivos=arquivos,
            metricas=_metricas_informadas(entrada),
        )

    def coletar_metricas(self, item: dict, entrada: dict | None = None) -> dict[str, float]:
        return _metricas_informadas(entrada or {})
