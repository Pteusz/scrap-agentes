"""Adaptador Instagram sem rede: a fonte é substituída por uma que serve dados gravados."""
import shutil

import pytest

from scrapagentes import adaptadores
from scrapagentes.adaptadores.base import (
    Bloqueado, ExigeLogin, FormatoNaoSuportado, Indisponivel, NaoEncontrado,
)
from scrapagentes.adaptadores.instagram import (
    AdaptadorInstagram, DadosPost, Limitador, MidiaRemota, classificar, extrair_shortcode,
    metricas_de, validar_proxy,
)
from scrapagentes.contrato import Exemplo, ExemploErro, verificar_adaptador

DATA = "2026-06-01T12:30:00+00:00"


def _post(shortcode, tipo, midias, **extra):
    base = dict(
        shortcode=shortcode, tipo=tipo, conta="conta_exemplo", data_utc=DATA, legenda="legenda #um",
        curtidas=120, comentarios=7, visualizacoes=None, duracao_s=None, midias=midias,
    )
    base.update(extra)
    return DadosPost(**base)


GRAVADOS = {
    "FOTO000001": _post("FOTO000001", "GraphImage", [MidiaRemota("https://cdn.exemplo/f.jpg", False)]),
    "REEL000001": _post(
        "REEL000001", "GraphVideo", [MidiaRemota("https://cdn.exemplo/v.mp4", True)],
        visualizacoes=5400, curtidas=-1,
    ),
    "CARR000001": _post(
        "CARR000001", "GraphSidecar",
        [MidiaRemota("https://cdn.exemplo/s1.jpg", False), MidiaRemota("https://cdn.exemplo/s2.jpg", False)],
    ),
    "MISTO00001": _post(
        "MISTO00001", "GraphSidecar",
        [MidiaRemota("https://cdn.exemplo/s1.jpg", False), MidiaRemota("https://cdn.exemplo/v.mp4", True)],
    ),
}
ERROS = {
    "SUMIU00001": NaoEncontrado("x"), "BLOQ000001": Bloqueado("x"),
    "PRIV000001": ExigeLogin("x"), "CAIU000001": Indisponivel("x"),
}


class FonteGravada:
    def __init__(self, midias):
        self.arquivos = {
            "https://cdn.exemplo/f.jpg": midias["foto"],
            "https://cdn.exemplo/v.mp4": midias["video"],
            "https://cdn.exemplo/s1.jpg": midias["slides"][0],
            "https://cdn.exemplo/s2.jpg": midias["slides"][1],
        }
        self.consultas = []

    def obter(self, shortcode):
        self.consultas.append(shortcode)
        if shortcode in ERROS:
            raise ERROS[shortcode]
        return GRAVADOS[shortcode]

    def baixar(self, url, destino):
        shutil.copy(self.arquivos[url], destino)
        return destino


@pytest.fixture
def adaptador(midias, tmp_path):
    return AdaptadorInstagram(fonte=FonteGravada(midias), pasta_tmp=tmp_path)


# ---------- URL ----------

@pytest.mark.parametrize("url", [
    "https://www.instagram.com/p/AbC_d-1/",
    "http://instagram.com/p/AbC_d-1",
    "https://www.instagram.com/reel/AbC_d-1/?utm_source=ig_web_copy_link&xtok=1",
    "https://www.instagram.com/reels/AbC_d-1/",
    "https://www.instagram.com/tv/AbC_d-1/",
    "https://m.instagram.com/some.user/reel/AbC_d-1/",
    "  https://www.instagram.com/p/AbC_d-1/#x  ",
])
def test_canoniza_para_a_mesma_url(url):
    a = AdaptadorInstagram(fonte=object())
    assert a.reconhece(url)
    assert a.canonizar_url(url) == "https://www.instagram.com/p/AbC_d-1/"


@pytest.mark.parametrize("url", [
    "", "https://www.instagram.com/", "https://www.instagram.com/alguem/",
    "https://www.instagram.com/stories/alguem/123/", "https://exemplo.com/p/AbC/",
    "https://instagram.com.malicioso.com/p/AbC/", "ftp://www.instagram.com/p/AbC/",
    "https://www.instagram.com/p/AbC/extra/",
])
def test_rejeita_o_que_nao_e_post(url):
    a = AdaptadorInstagram(fonte=object())
    assert not a.reconhece(url)
    with pytest.raises(ValueError):
        a.canonizar_url(url)


def test_extrair_shortcode():
    assert extrair_shortcode("https://www.instagram.com/reel/DczJptKyQtf/?x=1") == "DczJptKyQtf"


# ---------- regras ----------

def test_classificacao():
    assert classificar(GRAVADOS["FOTO000001"]) == "foto"
    assert classificar(GRAVADOS["REEL000001"]) == "video"
    assert classificar(GRAVADOS["CARR000001"]) == "carrossel"
    with pytest.raises(FormatoNaoSuportado):
        classificar(GRAVADOS["MISTO00001"])
    with pytest.raises(Indisponivel):
        classificar(_post("X", "GraphImage", []))
    with pytest.raises(FormatoNaoSuportado):
        classificar(_post("X", "GraphStoryQualquer", [MidiaRemota("https://a/b.jpg", False)]))


def test_metricas_omitem_o_que_nao_veio():
    assert metricas_de(GRAVADOS["REEL000001"]) == {"comentarios": 7.0, "visualizacoes": 5400.0}
    assert metricas_de(GRAVADOS["FOTO000001"]) == {"curtidas": 120.0, "comentarios": 7.0}
    assert metricas_de(_post("X", "GraphImage", [], curtidas=0)) == {"curtidas": 0.0, "comentarios": 7.0}


def test_dados_ida_e_volta_de_dict():
    from dataclasses import asdict
    d = GRAVADOS["CARR000001"]
    assert DadosPost.de_dict(asdict(d)) == d


# ---------- contrato ----------

def test_passa_na_suite_de_contrato(adaptador):
    verificar_adaptador(
        adaptador,
        [Exemplo("https://www.instagram.com/p/FOTO000001/"),
         Exemplo("https://www.instagram.com/reel/REEL000001/?utm_source=x"),
         Exemplo("https://www.instagram.com/p/CARR000001/")],
        [ExemploErro("https://www.instagram.com/p/SUMIU00001/", NaoEncontrado),
         ExemploErro("https://www.instagram.com/p/BLOQ000001/", Bloqueado),
         ExemploErro("https://www.instagram.com/p/PRIV000001/", ExigeLogin),
         ExemploErro("https://www.instagram.com/p/CAIU000001/", Indisponivel),
         ExemploErro("https://www.instagram.com/p/MISTO00001/", FormatoNaoSuportado)],
    )


def test_resolver_devolve_pasta_temporaria_com_a_midia(adaptador):
    r = adaptador.resolver("https://www.instagram.com/reel/REEL000001/")
    assert r.formato == "video" and r.duracao_s > 0
    assert r.pasta_temporaria and all(a.parent == r.pasta_temporaria for a in r.arquivos)


def test_falha_no_download_nao_deixa_pasta(midias, tmp_path):
    fonte = FonteGravada(midias)
    fonte.baixar = lambda url, destino: (_ for _ in ()).throw(Indisponivel("cdn fora"))
    a = AdaptadorInstagram(fonte=fonte, pasta_tmp=tmp_path)
    with pytest.raises(Indisponivel):
        a.resolver("https://www.instagram.com/p/FOTO000001/")
    assert list(tmp_path.iterdir()) == []


def test_coletar_metricas_nao_baixa_midia(midias, tmp_path):
    fonte = FonteGravada(midias)
    fonte.baixar = lambda *a: pytest.fail("não deveria baixar")
    a = AdaptadorInstagram(fonte=fonte, pasta_tmp=tmp_path)
    m = a.coletar_metricas({"url": "https://www.instagram.com/p/FOTO000001/"})
    assert m == {"curtidas": 120.0, "comentarios": 7.0}


# ---------- limitador e proxy ----------

def test_limitador_espera_so_o_que_falta():
    agora = [100.0]
    dormiu = []

    def dormir(s):
        dormiu.append(s)
        agora[0] += s

    lim = Limitador(5, relogio=lambda: agora[0], dormir=dormir)
    lim.esperar()            # primeira: sem espera
    agora[0] += 2
    lim.esperar()            # faltam 3 s
    agora[0] += 10
    lim.esperar()            # já passou o intervalo
    assert dormiu == [3]


def test_validar_proxy():
    assert validar_proxy(None) is None and validar_proxy("") is None
    assert validar_proxy("socks5h://127.0.0.1:1080") == "socks5h://127.0.0.1:1080"
    with pytest.raises(ValueError) as e:
        validar_proxy("ftp://usuario:segredo@host:1")
    assert "segredo" not in str(e.value)


def test_proxy_fora_do_ar_vira_indisponivel_sem_vazar_credencial(tmp_path):
    pytest.importorskip("instaloader")
    from scrapagentes.adaptadores.instagram import FonteInstaloader
    # porta 9 local: ninguém escuta, a conexão é recusada na hora
    proxy = "socks5h://usuario:segredo123@127.0.0.1:9"
    fonte = FonteInstaloader(proxy=proxy, intervalo_s=0, timeout_s=3)
    a = AdaptadorInstagram(fonte=fonte, pasta_tmp=tmp_path)
    with pytest.raises(Indisponivel) as e:
        a.resolver("https://www.instagram.com/p/AbCdEfGhIjK/")
    texto = f"{e.value} {e.value.__cause__!r} {e.value.__context__!r}"
    assert "segredo123" not in texto and "usuario" not in texto


# ---------- integração com o núcleo ----------

def test_ingestao_pela_api_limpa_a_pasta_temporaria(cliente, midias, tmp_path, monkeypatch, drenar):
    tmp = tmp_path / "ig-tmp"
    tmp.mkdir()
    monkeypatch.setitem(
        adaptadores._REGISTRO, "instagram",
        AdaptadorInstagram(fonte=FonteGravada(midias), pasta_tmp=tmp),
    )
    r = cliente.post("/itens", data={
        "url": "https://www.instagram.com/reel/REEL000001/?utm_source=x", "nicho": "Saúde",
        "subnichos": "treino",
    })
    assert r.status_code == 202, r.text
    drenar()
    job = cliente.get(f"/jobs/{r.json()['job_id']}").json()
    assert job["estado"] == "concluido", job
    assert list(tmp.iterdir()) == []
    ctx = cliente.get(f"/itens/{job['item_id']}/pacote").json()["contexto"]
    assert ctx["rede"] == "instagram" and ctx["link"] == "https://www.instagram.com/p/REEL000001/"
    assert ctx["formato"] == "video" and ctx["conta"] == "conta_exemplo"


def test_erro_do_adaptador_vira_job_com_erro_e_limpa(cliente, midias, tmp_path, monkeypatch, drenar):
    tmp = tmp_path / "ig-tmp"
    tmp.mkdir()
    monkeypatch.setitem(
        adaptadores._REGISTRO, "instagram",
        AdaptadorInstagram(fonte=FonteGravada(midias), pasta_tmp=tmp),
    )
    r = cliente.post("/itens", data={
        "url": "https://www.instagram.com/p/SUMIU00001/", "nicho": "saude",
    })
    drenar()
    job = cliente.get(f"/jobs/{r.json()['job_id']}").json()
    assert job["estado"] == "erro" and job["erro"].startswith("nao_encontrado")
    assert list(tmp.iterdir()) == []
