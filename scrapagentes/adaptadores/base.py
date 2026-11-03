"""Contrato do adaptador de rede (SPEC, seção 4).

O adaptador não escreve no banco, não transcreve e não extrai frames.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

METRICAS_PADRAO = frozenset(
    {"curtidas", "comentarios", "visualizacoes", "compartilhamentos", "seguidores_conta"}
)


class ErroAdaptador(Exception):
    codigo = "erro"


class NaoEncontrado(ErroAdaptador):
    codigo = "nao_encontrado"


class Bloqueado(ErroAdaptador):
    codigo = "bloqueado"


class ExigeLogin(ErroAdaptador):
    codigo = "exige_login"


class Indisponivel(ErroAdaptador):
    codigo = "indisponivel"


class FormatoNaoSuportado(ErroAdaptador):
    codigo = "formato_nao_suportado"


ERROS_TIPADOS = (NaoEncontrado, Bloqueado, ExigeLogin, Indisponivel, FormatoNaoSuportado)


@dataclass
class Resolvido:
    conta: str
    formato: str
    data_publicacao: str
    legenda: str
    duracao_s: float | None
    arquivos: list[Path]
    metricas: dict[str, float] = field(default_factory=dict)
    # Pasta temporária criada pelo adaptador para os arquivos; o núcleo a apaga depois de copiar.
    pasta_temporaria: Path | None = None


class Adaptador(ABC):
    nome: str
    formatos: tuple[str, ...]
    metricas_suportadas: frozenset[str]

    @abstractmethod
    def reconhece(self, url: str) -> bool:
        """Diz se a URL pertence a esta rede."""

    def canonizar_url(self, url: str, entrada: dict | None = None) -> str:
        """Devolve a URL canônica: a mesma rede + url é o mesmo item."""
        return url.strip()

    @abstractmethod
    def resolver(self, url: str, entrada: dict | None = None) -> Resolvido:
        """Obtém conta, formato, data, legenda, duração, mídia local e métricas iniciais."""

    @abstractmethod
    def coletar_metricas(self, item: dict, entrada: dict | None = None) -> dict[str, float]:
        """Devolve um mapa nome -> valor para o item já existente."""
