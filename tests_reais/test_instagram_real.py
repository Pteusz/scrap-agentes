"""Testes contra o Instagram de verdade. Só rodam com SCRAPAGENTES_TESTES_REAIS=1.

    SCRAPAGENTES_TESTES_REAIS=1 .venv/bin/python -m pytest tests_reais -m real -p no:cacheprovider

Usam o intervalo mínimo do adaptador (SCRAPAGENTES_IG_INTERVALO_S) e o proxy de SCRAPAGENTES_PROXY,
se houver. Números de curtidas mudam com o tempo: os testes checam tipo e ordem de grandeza.
"""
import os
import shutil

import pytest

from scrapagentes.adaptadores.base import ErroAdaptador
from scrapagentes.adaptadores.instagram import AdaptadorInstagram

pytestmark = [
    pytest.mark.real,
    pytest.mark.skipif(os.environ.get("SCRAPAGENTES_TESTES_REAIS") != "1", reason="defina SCRAPAGENTES_TESTES_REAIS=1"),
]

FOTO = "https://www.instagram.com/p/DfSJbEzDXf5/"
CARROSSEL = "https://www.instagram.com/p/Cyn3G8FLV1v/"
REELS = [f"https://www.instagram.com/reel/{c}/" for c in
         ("DczJptKyQtf", "De2QnoYB5Xe", "Db8eACCzSvD", "De0R33YN7r2")]
REEL_COM_FALHA = "https://www.instagram.com/reel/DfSLSZpjl_4/"  # field_exception no servidor do Instagram


@pytest.fixture(scope="module")
def adaptador():
    return AdaptadorInstagram()


def _resolver(adaptador, url):
    r = adaptador.resolver(url)
    try:
        yield r
    finally:
        shutil.rmtree(r.pasta_temporaria, ignore_errors=True)


@pytest.fixture
def foto(adaptador):
    yield from _resolver(adaptador, FOTO)


@pytest.fixture
def carrossel(adaptador):
    yield from _resolver(adaptador, CARROSSEL)


def test_foto(foto):
    assert foto.formato == "foto" and len(foto.arquivos) == 1 and foto.duracao_s is None
    assert foto.conta and foto.metricas.get("curtidas", 0) >= 0


def test_carrossel(carrossel):
    assert carrossel.formato == "carrossel" and len(carrossel.arquivos) >= 2
    assert [a.name[:3] for a in carrossel.arquivos] == sorted(a.name[:3] for a in carrossel.arquivos)


@pytest.mark.parametrize("url", REELS)
def test_reels(adaptador, url):
    r = adaptador.resolver(url)
    try:
        assert r.formato == "video" and r.duracao_s > 0 and len(r.arquivos) == 1
        assert r.metricas.get("curtidas", 0) > 0
    finally:
        shutil.rmtree(r.pasta_temporaria, ignore_errors=True)


def test_reel_com_falha_do_servidor_vira_erro_tipado(adaptador):
    with pytest.raises(ErroAdaptador):
        adaptador.resolver(REEL_COM_FALHA)


def test_post_inexistente(adaptador):
    with pytest.raises(ErroAdaptador) as e:
        adaptador.resolver("https://www.instagram.com/p/ZZZZZZZZZZZ/")
    assert e.value.codigo in {"nao_encontrado", "indisponivel"}
