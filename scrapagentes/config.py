"""Configuração lida de variáveis de ambiente. Segredos nunca ficam no repositório."""
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    dados: Path
    chave_api: str | None = None
    docs: bool = False
    ffmpeg: str | None = None

    @property
    def banco(self) -> Path:
        return self.dados / "scrapagentes.sqlite"

    @property
    def midia(self) -> Path:
        return self.dados / "midia"

    @classmethod
    def do_ambiente(cls) -> "Config":
        return cls(
            dados=Path(os.environ.get("SCRAPAGENTES_DADOS", "dados")).resolve(),
            chave_api=os.environ.get("SCRAPAGENTES_CHAVE_API") or None,
            docs=os.environ.get("SCRAPAGENTES_DOCS") == "1",
            ffmpeg=os.environ.get("SCRAPAGENTES_FFMPEG") or None,
        )
