"""Etapa 06: ingestão de vídeo com transcrição (simulada) e frames reais, pacote e busca."""
import json
import sqlite3

import pytest

from scrapagentes import servico, transcricao

TRECHOS = [
    {"inicio_s": 0.0, "fim_s": 1.5, "texto": "abertura sobre colágeno"},
    {"inicio_s": 3.0, "fim_s": 4.0, "texto": "meio da aula"},
]


@pytest.fixture
def com_fala(monkeypatch):
    monkeypatch.setattr(servico, "transcrever_video", lambda arquivo, ffmpeg=None: TRECHOS)


def test_video_vira_pacote_com_texto_e_imagens_em_ordem(envio, cliente, config, com_fala):
    item_id = envio.criar(envio.video, subnichos=["aula"])
    p = cliente.get(f"/itens/{item_id}/pacote").json()
    assert set(p) == {"contexto", "metricas", "texto", "imagens"}
    assert p["texto"] == TRECHOS
    d = p["contexto"]["duracao_s"]
    imgs = p["imagens"]
    assert len(imgs) >= 1
    assert [i["ordem"] for i in imgs] == list(range(1, len(imgs) + 1))
    segundos = [i["segundo"] for i in imgs]
    assert segundos == sorted(segundos)
    for i in imgs:
        assert set(i) == {"ordem", "rota", "segundo", "marcador", "fala_proxima"}
        esperado = "comeco" if i["segundo"] < d / 3 else "meio" if i["segundo"] < 2 * d / 3 else "fim"
        assert i["marcador"] == esperado
        r = cliente.get(i["rota"])
        assert r.status_code == 200 and r.content[:2] == b"\xff\xd8"  # JPEG
    assert not list(config.dados.glob("processamento-*"))


def test_fala_proxima_em_caso_construido():
    # 2,0 s: entre os dois trechos, a 0,5 s do primeiro e a 1,0 s do segundo -> primeiro
    assert servico._fala_proxima(TRECHOS, 2.0) == "abertura sobre colágeno"
    assert servico._fala_proxima(TRECHOS, 3.5) == "meio da aula"      # contido
    assert servico._fala_proxima(TRECHOS, 9.0) == "meio da aula"      # depois de tudo
    assert servico._fala_proxima([], 1.0) is None


def test_busca_acha_o_texto_falado(envio, cliente, com_fala):
    item_id = envio.criar(envio.video, legenda="outra coisa")
    envio.criar(envio.foto, legenda="sem relação")
    r = cliente.get("/itens", params={"q": "colágeno"}).json()
    assert [i["id"] for i in r["itens"]] == [item_id]


def test_video_sem_audio_fica_com_texto_vazio(envio, cliente, monkeypatch):
    def sem_audio(arquivo, ffmpeg=None):
        raise transcricao.ErroTranscricao("sem faixa de áudio")
    monkeypatch.setattr(servico, "transcrever_video", sem_audio)
    item_id = envio.criar(envio.video)
    p = cliente.get(f"/itens/{item_id}/pacote").json()
    assert p["texto"] == [] and len(p["imagens"]) >= 1


def test_reprocessar_video_refaz_texto_e_imagens(envio, cliente, config, monkeypatch):
    item_id = envio.criar(envio.video, url="manual:v1")
    assert cliente.get(f"/itens/{item_id}/pacote").json()["texto"] == []
    monkeypatch.setattr(servico, "transcrever_video", lambda arquivo, ffmpeg=None: TRECHOS)
    envio.criar(envio.video, url="manual:v1", reprocessar="true")
    p = cliente.get(f"/itens/{item_id}/pacote").json()
    assert p["texto"] == TRECHOS and len(p["imagens"]) >= 1


def test_falha_nos_frames_vira_job_com_erro_sem_sobras(envio, cliente, config, monkeypatch):
    from scrapagentes import frames

    def quebra(*a, **k):
        raise frames.ErroFrames("não foi possível ler os quadros do vídeo")
    monkeypatch.setattr(servico, "selecionar_frames", quebra)
    r = envio.video()
    job = cliente.get(f"/jobs/{r.json()['job_id']}").json()
    assert job["estado"] == "erro"
    assert not list(config.dados.glob("processamento-*"))
    conn = sqlite3.connect(config.banco)
    assert conn.execute("SELECT COUNT(*) FROM item").fetchone()[0] == 0


def test_metrica_mais_recente_no_pacote_e_na_busca(envio, cliente):
    item_id = envio.criar(envio.video, metricas=json.dumps({"curtidas": 10}))
    cliente.post(f"/itens/{item_id}/coletas", json={"metricas": {"curtidas": 50}})
    p = cliente.get(f"/itens/{item_id}/pacote").json()
    assert p["metricas"]["valores"]["curtidas"] == 50
    assert [i["id"] for i in cliente.get("/itens", params={"metrica": "curtidas", "min": 40}).json()["itens"]] == [item_id]
    assert cliente.get("/itens", params={"metrica": "curtidas", "max": 20}).json()["total"] == 0
