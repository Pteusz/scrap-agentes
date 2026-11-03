"""Etapa 09: limites da API e backup."""
import sqlite3
from dataclasses import replace
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from scrapagentes import backup
from scrapagentes.api import criar_app

CHAVE = "chave-de-teste"


def _cliente(config, **mudancas):
    return TestClient(criar_app(replace(config, **mudancas)), headers={"X-API-Key": config.chave_api})


def test_corpo_acima_do_limite_da_413(config):
    with _cliente(config, upload_max_mib=1) as c:
        r = c.post("/itens", content=b"x" * (1024 * 1024 + 1), headers={"content-type": "application/json"})
        assert r.status_code == 413
        assert "MiB" in r.json()["detail"]
        # corpo dentro do limite continua passando (e cai na validação normal)
        assert c.post("/itens", json={}).status_code == 422


def test_corpo_sem_content_length_tambem_e_contado(config):
    with _cliente(config, upload_max_mib=1) as c:
        def pedacos():
            for _ in range(3):
                yield b"x" * (512 * 1024)

        r = c.post("/itens", content=pedacos(), headers={"content-type": "application/json"})
        assert r.status_code == 413


def test_limite_de_requisicoes_por_chave(config):
    with _cliente(config, requisicoes_por_minuto=5) as c:
        codigos = [c.get("/itens").status_code for _ in range(7)]
        assert codigos == [200] * 5 + [429] * 2
        r = c.get("/itens")
        assert int(r.headers["retry-after"]) >= 1
        assert c.get("/saude").status_code == 200            # /saude fica livre
        outra = c.get("/itens", headers={"X-API-Key": "outra-chave"})
        assert outra.status_code == 401                      # o balde da chave válida cheio não afeta os outros


def test_chaves_erradas_dividem_um_balde_e_sao_freadas(config):
    with TestClient(criar_app(replace(config, requisicoes_por_minuto=3))) as c:
        codigos = [c.get("/itens", headers={"X-API-Key": f"chute-{i}"}).status_code for i in range(5)]
        assert codigos[:3] == [401] * 3 and codigos[3:] == [429, 429]


def test_chave_nao_aparece_na_resposta_de_limite(config):
    with _cliente(config, requisicoes_por_minuto=1) as c:
        c.get("/itens")
        r = c.get("/itens")
        assert r.status_code == 429 and CHAVE not in r.text


def _popular(envio, config):
    envio.criar(envio.carrossel, url="manual:b1", curtidas="3", subnichos=["a"])
    envio.criar(envio.foto, url="manual:b2", curtidas="5")


def test_backup_restaura_com_os_dados(envio, config, tmp_path):
    _popular(envio, config)
    destino = tmp_path / "bk"
    pasta = backup.criar(config.dados, destino)
    # muda o original depois: o backup não pode acompanhar
    c = sqlite3.connect(config.banco)
    c.execute("DELETE FROM metrica")
    c.commit()
    c.close()
    r = backup.verificar(pasta)
    assert r["itens"] == 2 and r["metricas"] == 2 and r["imagens"] >= 3
    assert r["arquivos_de_midia"] == r["imagens"]


def test_backup_ignora_midia_em_troca_e_mantem_so_os_recentes(envio, config, tmp_path):
    _popular(envio, config)
    (config.dados / "midia" / "99.novo").mkdir()
    (config.dados / "midia" / "99.novo" / "001.jpg").write_bytes(b"x")
    destino = tmp_path / "bk"
    agora = datetime(2026, 11, 10, 3, 0, 0)
    for dias in (9, 8, 6, 1):
        backup.criar(config.dados, destino, 7, agora - timedelta(days=dias))
    pasta = backup.criar(config.dados, destino, 7, agora)
    assert not (pasta / "midia" / "99.novo").exists()
    nomes = sorted(p.name for p in destino.iterdir())
    assert nomes == ["backup-20261104-030000", "backup-20261109-030000", "backup-20261110-030000"]


def test_backup_com_banco_ausente_falha_sem_deixar_lixo(tmp_path):
    with pytest.raises(FileNotFoundError):
        backup.criar(tmp_path / "vazio", tmp_path / "bk")
    assert not (tmp_path / "bk").exists() or not list((tmp_path / "bk").iterdir())
