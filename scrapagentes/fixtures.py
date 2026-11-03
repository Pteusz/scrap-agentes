"""Gera fixtures determinísticas com ffmpeg, sem depender de arquivos externos.

Uso: python -m scrapagentes.fixtures [pasta]

Produz: video.mp4 (3 cenas de cores diferentes, 2 s cada, com tom de 440 Hz), foto.png e
slide_1.png, slide_2.png, slide_3.png (carrossel).
"""
import subprocess
import sys
from pathlib import Path

from scrapagentes.midia import localizar_ffmpeg

TAMANHO = "320x240"
CORES_CENAS = ("red", "green", "blue")
CORES_SLIDES = ("orange", "purple", "teal")
DURACAO_CENA_S = 2


def _ffmpeg(*args: str) -> None:
    cmd = [localizar_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", *args]
    subprocess.run(cmd, check=True, timeout=120)


def _imagem(cor: str, destino: Path) -> None:
    _ffmpeg(
        "-f", "lavfi", "-i", f"color=c={cor}:s={TAMANHO}",
        "-frames:v", "1", "-map_metadata", "-1", "-fflags", "+bitexact", str(destino),
    )


def gerar_fixtures(pasta: Path) -> dict:
    pasta.mkdir(parents=True, exist_ok=True)
    entradas = []
    for cor in CORES_CENAS:
        entradas += ["-f", "lavfi", "-i", f"color=c={cor}:s={TAMANHO}:r=25:d={DURACAO_CENA_S}"]
    total = DURACAO_CENA_S * len(CORES_CENAS)
    entradas += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={total}"]
    video = pasta / "video.mp4"
    _ffmpeg(
        *entradas,
        "-filter_complex", f"[0:v][1:v][2:v]concat=n={len(CORES_CENAS)}:v=1:a=0[v]",
        "-map", "[v]", "-map", f"{len(CORES_CENAS)}:a",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
        "-map_metadata", "-1", "-fflags", "+bitexact", "-flags:v", "+bitexact",
        "-flags:a", "+bitexact", str(video),
    )
    foto = pasta / "foto.png"
    _imagem("yellow", foto)
    slides = []
    for i, cor in enumerate(CORES_SLIDES, start=1):
        destino = pasta / f"slide_{i}.png"
        _imagem(cor, destino)
        slides.append(destino)
    return {"video": video, "duracao_video_s": float(total), "foto": foto, "slides": slides}


if __name__ == "__main__":
    destino = Path(sys.argv[1] if len(sys.argv) > 1 else "fixtures")
    for nome, caminho in gerar_fixtures(destino).items():
        print(nome, caminho)
