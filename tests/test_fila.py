"""Etapa 07: fila na tabela `job`, worker, retentativas, recuperação e idempotência."""
import shutil
import sqlite3
import threading

import pytest

from scrapagentes import servico, trabalhador, transcricao
from scrapagentes.adaptadores.base import Indisponivel
from scrapagentes.adaptadores.manual import AdaptadorManual


def _contar(config, tabela, onde="1=1"):
    c = sqlite3.connect(config.banco)
    try:
        return c.execute(f"SELECT COUNT(*) FROM {tabela} WHERE {onde}").fetchone()[0]
    finally:
        c.close()


def _job(cliente, resposta):
    return cliente.get(f"/jobs/{resposta.json()['job_id']}").json()


def _cai(*a, **k):
    raise servico.Queda()


@pytest.fixture
def falha_em_url_falha(monkeypatch):
    """Adaptador manual que falha (erro transitório) nas urls que contêm 'falha'."""
    original = AdaptadorManual.resolver

    def resolver(self, url, entrada=None):
        if "falha" in url:
            raise Indisponivel("rede fora do ar")
        return original(self, url, entrada)

    monkeypatch.setattr(AdaptadorManual, "resolver", resolver)


def test_ciclo_completo_api_enfileira_e_worker_executa(envio, cliente, config):
    r = envio.carrossel(executar=False, subnichos=["a"], curtidas="7")
    assert r.status_code == 202
    assert _job(cliente, r)["estado"] == "pendente"
    assert _contar(config, "item") == 0                      # a API não processou nada
    assert trabalhador.rodar(config, uma_vez=True) == 1
    job = _job(cliente, r)
    assert job["estado"] == "concluido" and job["erro"] is None
    p = cliente.get(f"/itens/{job['item_id']}/pacote").json()
    assert len(p["imagens"]) >= 2
    assert p["metricas"]["valores"] == {"curtidas": 7.0}
    assert not (config.dados / "entrada" / str(job["id"])).exists()  # upload de entrada limpo


def test_falha_forcada_registra_cada_tentativa_e_outros_jobs_seguem(envio, cliente, falha_em_url_falha):
    ruim = envio.foto(executar=False, url="manual:falha-1")
    bom = envio.foto(executar=False, url="manual:ok-1")
    outro = envio.foto(executar=False, url="manual:ok-2")
    envio.drenar()
    j = _job(cliente, ruim)
    assert j["estado"] == "erro" and j["tentativas"] == 3          # 1 execução + 2 retentativas
    linhas = j["erro"].splitlines()
    assert len(linhas) == 3
    assert all("indisponivel" in l and "rede fora do ar" in l for l in linhas)
    assert linhas[0].startswith("tentativa 1/3") and linhas[2].startswith("tentativa 3/3")
    assert _job(cliente, bom)["estado"] == "concluido"
    assert _job(cliente, outro)["estado"] == "concluido"


def test_retentativa_que_funciona_conclui(envio, cliente, monkeypatch):
    original = AdaptadorManual.resolver
    chamadas = []

    def resolver(self, url, entrada=None):
        chamadas.append(1)
        if len(chamadas) < 3:
            raise Indisponivel("instável")
        return original(self, url, entrada)

    monkeypatch.setattr(AdaptadorManual, "resolver", resolver)
    j = _job(cliente, envio.foto(url="manual:instavel"))
    assert j["estado"] == "concluido" and j["tentativas"] == 3
    assert j["item_id"] is not None


def test_erro_definitivo_nao_tem_retentativa(envio, cliente):
    r = envio.foto(formato="video", url="manual:x")  # imagem enviada como vídeo: formato_nao_suportado
    j = _job(cliente, r)
    assert j["estado"] == "erro" and j["tentativas"] == 1
    assert j["erro"].startswith("formato_nao_suportado") and "\n" not in j["erro"]


def test_queda_antes_do_commit_reinicio_retoma_sem_duplicar(envio, cliente, config, monkeypatch):
    with monkeypatch.context() as m:
        m.setattr(servico, "reindexar_busca", _cai)
        r = envio.foto(executar=False, url="manual:q1", curtidas="3", subnichos=["x"])
        with pytest.raises(servico.Queda):
            trabalhador.rodar(config, uma_vez=True)
    assert _job(cliente, r)["estado"] == "executando"             # ficou preso: o processo morreu
    assert _contar(config, "item") == 0 and _contar(config, "metrica") == 0

    trabalhador.rodar(config, uma_vez=True)                       # worker reinicia
    j = _job(cliente, r)
    assert j["estado"] == "concluido" and j["tentativas"] == 2
    assert "interrompido" in j["erro"]                            # a queda ficou registrada
    assert _contar(config, "item") == 1
    assert _contar(config, "imagem") == 1
    assert _contar(config, "metrica") == 1
    assert _contar(config, "subnicho") == 1


def test_queda_depois_do_commit_antes_de_trocar_a_midia(envio, cliente, config, monkeypatch):
    with monkeypatch.context() as m:
        m.setattr(servico, "_trocar_midia", _cai)
        r = envio.carrossel(executar=False, url="manual:q2", curtidas="3")
        with pytest.raises(servico.Queda):
            trabalhador.rodar(config, uma_vez=True)
    # o commit aconteceu (item, imagens, métrica e job fechado juntos); a pasta ficou como .novo
    j = _job(cliente, r)
    assert j["estado"] == "concluido"
    item_id = j["item_id"]
    assert (config.dados / "midia" / f"{item_id}.novo").is_dir()

    assert trabalhador.rodar(config, uma_vez=True) == 0           # reinício só conclui a troca
    assert not (config.dados / "midia" / f"{item_id}.novo").exists()
    assert (config.dados / "midia" / str(item_id)).is_dir()
    assert cliente.get(f"/itens/{item_id}/imagens/1").status_code == 200
    assert _contar(config, "item") == 1 and _contar(config, "metrica") == 1


def test_job_que_derruba_o_worker_repetidamente_esgota_as_tentativas(envio, cliente, config, monkeypatch):
    r = envio.foto(executar=False, url="manual:veneno")
    monkeypatch.setattr(servico, "reindexar_busca", _cai)
    for _ in range(servico.MAX_TENTATIVAS):
        with pytest.raises(servico.Queda):
            trabalhador.rodar(config, uma_vez=True)
    trabalhador.rodar(config, uma_vez=True)
    j = _job(cliente, r)
    assert j["estado"] == "erro" and j["tentativas"] == 3
    assert "interrompido" in j["erro"]


def test_recuperacao_limpa_sobras_de_processamento(config):
    (config.dados / "processamento-abc").mkdir(parents=True)
    trabalhador.rodar(config, uma_vez=True)
    assert not (config.dados / "processamento-abc").exists()


def test_dois_jobs_de_video_executam_em_sequencia(envio, cliente, config, monkeypatch):
    eventos, lock = [], threading.Lock()

    def lenta(arquivo, ffmpeg=None):
        with transcricao.TravaDeTrabalho():  # a mesma trava da transcrição real
            with lock:
                eventos.append("inicio")
            threading.Event().wait(0.3)
            with lock:
                eventos.append("fim")
        return []

    monkeypatch.setattr(servico, "transcrever_video", lenta)
    a = envio.video(executar=False, url="manual:v1")
    b = envio.video(executar=False, url="manual:v2")
    # dois workers ao mesmo tempo: cada job roda uma única vez e os trechos pesados não se sobrepõem
    ts = [threading.Thread(target=trabalhador.rodar, args=(config,), kwargs={"uma_vez": True}) for _ in range(2)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert eventos == ["inicio", "fim", "inicio", "fim"]
    ja, jb = _job(cliente, a), _job(cliente, b)
    assert ja["estado"] == jb["estado"] == "concluido" and ja["tentativas"] == jb["tentativas"] == 1
    assert _contar(config, "item") == 2


def test_reingestao_enfileirada_duas_vezes_nao_duplica(envio, cliente, config):
    r1 = envio.foto(executar=False, url="manual:dup", curtidas="1", subnichos=["a"])
    r2 = envio.foto(executar=False, url="manual:dup", curtidas="2", subnichos=["a"])
    envio.drenar()
    assert _job(cliente, r1)["item_id"] == _job(cliente, r2)["item_id"]
    assert _contar(config, "item") == 1 and _contar(config, "imagem") == 1
    assert _contar(config, "subnicho") == 1
    c = sqlite3.connect(config.banco)
    assert len(c.execute("SELECT DISTINCT coletado_em FROM metrica").fetchall()) == 2
    c.close()


def test_reprocessar_refaz_as_imagens_pela_fila(envio, cliente, config):
    item_id = envio.criar(envio.carrossel, url="manual:rep")
    antes = _contar(config, "imagem")
    arq = sorted((config.dados / "midia" / str(item_id)).iterdir())[0]
    arq.write_bytes(b"corrompido")
    envio.criar(envio.carrossel, url="manual:rep")                # sem reprocessar: não toca
    assert arq.read_bytes() == b"corrompido"
    envio.criar(envio.carrossel, url="manual:rep", reprocessar="true")
    assert arq.read_bytes() != b"corrompido"
    assert _contar(config, "imagem") == antes and _contar(config, "item") == 1


def test_item_sem_pasta_de_midia_e_refeito_na_reingestao(envio, cliente, config):
    item_id = envio.criar(envio.carrossel, url="manual:perdida")
    shutil.rmtree(config.dados / "midia" / str(item_id))
    envio.criar(envio.carrossel, url="manual:perdida")
    assert (config.dados / "midia" / str(item_id)).is_dir()
    assert _contar(config, "item") == 1


def test_coleta_pela_fila(envio, cliente, config):
    item_id = envio.criar(envio.foto, url="manual:c", curtidas="1")
    r = cliente.post(f"/itens/{item_id}/coletas", json={"metricas": {"curtidas": 9}})
    assert _job(cliente, r)["estado"] == "pendente"
    envio.drenar()
    assert _job(cliente, r)["estado"] == "concluido"
    assert _contar(config, "metrica", "nome = 'curtidas'") == 2
