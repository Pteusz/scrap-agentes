import pytest

from scrapagentes.adaptadores.base import (
    Adaptador, FormatoNaoSuportado, NaoEncontrado, Resolvido,
)
from scrapagentes.adaptadores.manual import AdaptadorManual
from scrapagentes.contrato import Exemplo, ExemploErro, verificar_adaptador


def _entrada(formato, arquivos, **extra):
    base = {"conta": "c", "formato": formato, "data_publicacao": "2026-03-10", "arquivos": arquivos}
    base.update(extra)
    return base


def test_manual_passa_na_suite_de_contrato(midias, tmp_path):
    vazio = tmp_path / "vazio.png"
    vazio.write_bytes(b"")
    verificar_adaptador(
        AdaptadorManual(),
        exemplos=[
            Exemplo("", _entrada("video", [midias["video"]], metricas={"curtidas": 10})),
            Exemplo("", _entrada("foto", [midias["foto"]])),
            Exemplo("", _entrada("carrossel", midias["slides"], metricas={"comentarios": 2.5})),
        ],
        exemplos_erro=[
            ExemploErro("", FormatoNaoSuportado, _entrada("reels", [midias["foto"]])),
            ExemploErro("", FormatoNaoSuportado, _entrada("carrossel", [midias["foto"]])),
            ExemploErro("", NaoEncontrado, _entrada("foto", [tmp_path / "nao_existe.png"])),
            ExemploErro("", NaoEncontrado, _entrada("foto", [vazio])),
        ],
    )


class _Defeituoso(Adaptador):
    """Adaptador que viola o contrato de propósito, para provar que a suite o pega."""
    nome = "defeituoso"
    formatos = ("foto",)
    metricas_suportadas = frozenset({"curtidas"})

    def __init__(self, resolvido):
        self._resolvido = resolvido

    def reconhece(self, url):
        return True

    def resolver(self, url, entrada=None):
        return self._resolvido

    def coletar_metricas(self, item, entrada=None):
        return {}


def _ok(midias, **mudancas):
    base = dict(conta="c", formato="foto", data_publicacao="2026-03-10", legenda="",
                duracao_s=None, arquivos=[midias["foto"]], metricas={})
    base.update(mudancas)
    return Resolvido(**base)


@pytest.mark.parametrize("mudanca", [
    {"formato": "story"},
    {"conta": ""},
    {"data_publicacao": "ontem"},
    {"metricas": {"curtidas": "dez"}},
    {"metricas": {"inventada": 1}},
    {"duracao_s": 5.0},
])
def test_suite_pega_violacoes(midias, mudanca):
    with pytest.raises(AssertionError):
        verificar_adaptador(_Defeituoso(_ok(midias, **mudanca)), [Exemplo("x")])


def test_suite_aceita_adaptador_correto(midias):
    verificar_adaptador(_Defeituoso(_ok(midias)), [Exemplo("x")])
