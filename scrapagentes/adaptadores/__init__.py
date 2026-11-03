"""Registro de adaptadores de rede."""
from scrapagentes.adaptadores.base import Adaptador
from scrapagentes.adaptadores.instagram import AdaptadorInstagram
from scrapagentes.adaptadores.manual import AdaptadorManual

_REGISTRO: dict[str, Adaptador] = {}


def registrar(adaptador: Adaptador) -> None:
    _REGISTRO[adaptador.nome] = adaptador


def obter(nome: str) -> Adaptador | None:
    return _REGISTRO.get(nome)


def detectar(url: str) -> Adaptador | None:
    """Primeiro adaptador que reconhece a URL como sua."""
    for adaptador in _REGISTRO.values():
        if adaptador.reconhece(url):
            return adaptador
    return None


def nomes() -> list[str]:
    return sorted(_REGISTRO)


registrar(AdaptadorManual())
registrar(AdaptadorInstagram())  # a fonte real (Instaloader) só é criada na primeira consulta
