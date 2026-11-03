"""Etapa 08: métrica sob demanda. Só por chamada própria; nunca altera coletas anteriores."""
import re
import sqlite3
from pathlib import Path

import pytest

import scrapagentes
from scrapagentes.adaptadores.base import Bloqueado, NaoEncontrado
from scrapagentes.adaptadores.manual import AdaptadorManual


def _metricas(config, item_id):
    c = sqlite3.connect(config.banco)
    try:
        return c.execute(
            "SELECT coletado_em, nome, valor FROM metrica WHERE item_id = ? ORDER BY coletado_em, nome",
            (item_id,),
        ).fetchall()
    finally:
        c.close()


def _job(cliente, r):
    return cliente.get(f"/jobs/{r.json()['job_id']}").json()


def test_coleta_nao_acontece_sozinha(envio, cliente, config, drenar):
    item_id = envio.criar(envio.foto, curtidas="10")
    drenar()
    drenar()  # nada pendente: rodar o worker de novo não coleta nada
    assert len(_metricas(config, item_id)) == 1


def test_todas_as_linhas_de_uma_coleta_compartilham_coletado_em(envio, cliente, config, drenar):
    item_id = envio.criar(envio.foto, curtidas="10", comentarios="2")
    cliente.post(f"/itens/{item_id}/coletas", json={"metricas": {"curtidas": 11, "comentarios": 3}})
    cliente.post(f"/itens/{item_id}/coletas", json={"metricas": {"curtidas": 12, "comentarios": 4}})
    drenar()
    linhas = _metricas(config, item_id)
    datas = [l[0] for l in linhas]
    assert len(linhas) == 6 and len(set(datas)) == 3
    assert all(datas.count(d) == 2 for d in set(datas))


@pytest.mark.parametrize("erro", [Bloqueado("bloqueado pelo Instagram"), NaoEncontrado("post removido")])
def test_falha_do_adaptador_nao_toca_nas_coletas_anteriores(envio, cliente, config, drenar, monkeypatch, erro):
    item_id = envio.criar(envio.foto, curtidas="10", comentarios="2")
    antes = _metricas(config, item_id)

    def falha(self, item, entrada=None):
        raise erro

    monkeypatch.setattr(AdaptadorManual, "coletar_metricas", falha)
    r = cliente.post(f"/itens/{item_id}/coletas")
    drenar()
    job = _job(cliente, r)
    assert job["estado"] == "erro"
    assert erro.codigo in job["erro"] and str(erro) in job["erro"]
    assert _metricas(config, item_id) == antes
    pacote = cliente.get(f"/itens/{item_id}/pacote").json()
    assert pacote["metricas"]["valores"] == {"curtidas": 10.0, "comentarios": 2.0}


def test_item_de_rede_sem_adaptador_da_erro_claro(envio, cliente, config, drenar):
    item_id = envio.criar(envio.foto, curtidas="10")
    c = sqlite3.connect(config.banco)
    c.execute("UPDATE item SET rede = 'inexistente' WHERE id = ?", (item_id,))
    c.commit()
    c.close()
    r = cliente.post(f"/itens/{item_id}/coletas")
    assert r.status_code == 422
    assert "inexistente" in r.json()["detail"] and "adaptador" in r.json()["detail"]
    c = sqlite3.connect(config.banco)
    assert c.execute("SELECT COUNT(*) FROM job WHERE tipo = 'coleta'").fetchone()[0] == 0
    c.close()


def test_adaptador_removido_depois_de_enfileirar_vira_job_com_erro(envio, cliente, config, drenar):
    item_id = envio.criar(envio.foto, curtidas="10")
    r = cliente.post(f"/itens/{item_id}/coletas", json={"metricas": {"curtidas": 20}})
    c = sqlite3.connect(config.banco)
    c.execute("UPDATE item SET rede = 'inexistente' WHERE id = ?", (item_id,))
    c.commit()
    c.close()
    drenar()
    job = _job(cliente, r)
    assert job["estado"] == "erro" and "inexistente" in job["erro"]
    assert len(_metricas(config, item_id)) == 1


def test_nao_existe_agendador_nem_recoleta_automatica():
    """Varre o código de produção: nada de agendador, cron interno ou laço de recoleta."""
    proibidos = re.compile(
        r"apscheduler|schedule\b|sched\b|crontab|celery|threading\.Timer|BackgroundScheduler|"
        r"AsyncIOScheduler|asyncio\.sleep|call_later|repeat_every|on_event\(.startup|add_job",
        re.IGNORECASE,
    )
    raiz = Path(scrapagentes.__file__).parent
    achados = []
    for arq in raiz.rglob("*.py"):
        for n, linha in enumerate(arq.read_text(encoding="utf-8").splitlines(), 1):
            if proibidos.search(linha):
                achados.append(f"{arq.name}:{n}: {linha.strip()}")
    assert achados == []

    # a única origem de job de coleta é a chamada própria (enfileirar_coleta, usada só pela rota)
    usos = [a.name for a in raiz.rglob("*.py") if "enfileirar_coleta" in a.read_text(encoding="utf-8")]
    assert sorted(usos) == ["api.py", "servico.py"]
