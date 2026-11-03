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
    upload_max_mib: int = 200
    requisicoes_por_minuto: int = 120
    prazo_corpo_s: float = 300.0

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
            upload_max_mib=int(os.environ.get("SCRAPAGENTES_UPLOAD_MAX_MIB", 200)),
            requisicoes_por_minuto=int(os.environ.get("SCRAPAGENTES_REQUISICOES_POR_MIN", 120)),
            prazo_corpo_s=float(os.environ.get("SCRAPAGENTES_PRAZO_CORPO_S", 300)),
        )
