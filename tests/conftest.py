import pytest
from fastapi.testclient import TestClient

from scrapagentes.api import criar_app
from scrapagentes.config import Config
from scrapagentes.fixtures import gerar_fixtures

CHAVE = "chave-de-teste"


@pytest.fixture(scope="session")
def midias(tmp_path_factory):
    """Fixtures geradas com ffmpeg uma única vez por sessão de testes."""
    return gerar_fixtures(tmp_path_factory.mktemp("fixtures"))


@pytest.fixture
def config(tmp_path):
    return Config(dados=tmp_path / "dados", chave_api=CHAVE)


@pytest.fixture
def cliente(config):
    with TestClient(criar_app(config), headers={"X-API-Key": CHAVE}) as c:
        yield c


@pytest.fixture
def cliente_sem_chave(config):
    with TestClient(criar_app(config)) as c:
        yield c


class Envio:
    """Atalhos para enviar itens do adaptador manual pela API."""

    def __init__(self, cliente, midias):
        self.cliente, self.midias = cliente, midias

    def foto(self, **extra):
        return self._enviar("foto", [self.midias["foto"]], **extra)

    def carrossel(self, **extra):
        return self._enviar("carrossel", self.midias["slides"], **extra)

    def video(self, **extra):
        return self._enviar("video", [self.midias["video"]], **extra)

    def _enviar(self, formato_padrao, caminhos, **extra):
        dados = {
            "rede": "manual", "conta": "conta_teste", "formato": formato_padrao,
            "data_publicacao": "2026-03-10", "legenda": "legenda de teste", "nicho": "saude",
        }
        dados.update(extra)
        arquivos = [("arquivos", (p.name, p.read_bytes(), "application/octet-stream")) for p in caminhos]
        return self.cliente.post("/itens", data=dados, files=arquivos)

    def criar(self, enviar, **extra):
        r = enviar(**extra)
        assert r.status_code == 202, r.text
        corpo = r.json()
        job = self.cliente.get(f"/jobs/{corpo['job_id']}").json()
        assert job["estado"] == "concluido", job
        return corpo["item_id"]


@pytest.fixture
def envio(cliente, midias):
    return Envio(cliente, midias)
