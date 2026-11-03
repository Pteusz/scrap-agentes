"""Utilitários de mídia que dependem de ffmpeg."""
import os
import re
import shutil
import subprocess
from pathlib import Path


def localizar_ffmpeg(configurado: str | None = None) -> str:
    """Ordem: variável SCRAPAGENTES_FFMPEG, ffmpeg no PATH, binário do pacote imageio-ffmpeg."""
    candidato = configurado or os.environ.get("SCRAPAGENTES_FFMPEG")
    if candidato:
        return candidato
    achado = shutil.which("ffmpeg")
    if achado:
        return achado
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:  # pragma: no cover - depende do ambiente
        raise RuntimeError(
            "ffmpeg não encontrado: instale o ffmpeg ou o pacote imageio-ffmpeg, "
            "ou defina SCRAPAGENTES_FFMPEG"
        ) from exc


def duracao_video(caminho: Path, ffmpeg: str | None = None) -> float | None:
    """Duração em segundos lida da saída de `ffmpeg -i`. None se não for possível ler."""
    try:
        saida = subprocess.run(
            [localizar_ffmpeg(ffmpeg), "-hide_banner", "-i", str(caminho)],
            capture_output=True, text=True, timeout=60,
        ).stderr
    except (RuntimeError, OSError, subprocess.TimeoutExpired):
        return None
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", saida)
    if not m:
        return None
    h, mi, s = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(s)
