import pytest

from scrapagentes.fixtures import gerar_fixtures


@pytest.fixture(scope="session")
def midias(tmp_path_factory):
    return gerar_fixtures(tmp_path_factory.mktemp("fixtures"))
