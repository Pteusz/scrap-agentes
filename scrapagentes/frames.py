"""Seleção determinística de frames de um vídeo (SPEC, seção 6) e marcadores (seção 3).

Entra um vídeo; saem frames em ordem de tempo: {ordem, arquivo, segundo, marcador}, com as imagens
salvas em disco. Sem IA. Duas passadas baratas no ffmpeg (pontuação de cena e miniaturas em cinza
em grade regular de tempo); toda decisão é feita sobre essas miniaturas, só com inteiros e
médias, então a mesma entrada dá os mesmos segundos. As imagens finais são extraídas só dos
segundos escolhidos.

Parâmetros iniciais do SPEC em `ParametrosFrames`; cada um pode ser trocado por variável de
ambiente `SCRAPAGENTES_FRAMES_<NOME>` (ex.: SCRAPAGENTES_FRAMES_TETO=12).

Uso: python -m scrapagentes.frames <video> [--saida pasta] [--folha folha.jpg]
"""
import argparse
import dataclasses
import math
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from scrapagentes import midia
from scrapagentes.transcricao import TravaDeTrabalho

LARGURA, ALTURA = 160, 96  # miniatura de análise; 96 = 16*6 e 160 = 16*10 (grade 16x16 do hash)


class ErroFrames(Exception):
    pass


@dataclass(frozen=True)
class ParametrosFrames:
    limiar_cena: float = 0.20        # pontuação de mudança de cena do ffmpeg
    luma_minima: float = 16.0        # média de luminância abaixo disso = quase preto (0-255)
    nitidez_minima: float = 8.0      # variância do laplaciano abaixo disso (com textura) = muito borrado
    dedup_diferenca: float = 2.0     # diferença média absoluta (0-255) entre miniaturas 16x16
    minimo_candidatos: int = 8       # abaixo disso, completa com amostragem uniforme
    teto: int = 16
    minimo_por_terco: int = 2
    amostras_por_s: float = 4.0      # grade de análise
    max_amostras: int = 720
    diferenca_estavel: float = 6.0   # "frame estável": pouca diferença para a amostra anterior

    @classmethod
    def do_ambiente(cls) -> "ParametrosFrames":
        valores = {}
        for campo in dataclasses.fields(cls):
            bruto = os.environ.get(f"SCRAPAGENTES_FRAMES_{campo.name.upper()}")
            if bruto:
                valores[campo.name] = campo.type(bruto) if callable(campo.type) else float(bruto)
        return cls(**valores)


def marcador(t: float, d: float) -> str:
    """Regra do SPEC: t < d/3 comeco; d/3 <= t < 2d/3 meio; t >= 2d/3 fim."""
    if t < d / 3:
        return "comeco"
    if t < 2 * d / 3:
        return "meio"
    return "fim"


# ---------- leitura do vídeo (ffmpeg) ----------

def _pontuacoes_de_cena(video: Path, limiar: float, ffmpeg: str) -> list[float]:
    proc = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(video), "-an",
         "-vf", f"select='gt(scene,{limiar})',showinfo", "-f", "null", "-"],
        capture_output=True, text=True, timeout=900,
    )
    return [float(m) for m in re.findall(r"pts_time:\s*([0-9.]+)", proc.stderr)]


def _miniaturas(video: Path, fps: float, ffmpeg: str) -> np.ndarray:
    proc = subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(video), "-an",
         "-vf", f"fps={fps:.6f},scale={LARGURA}:{ALTURA}:flags=area,format=gray",
         "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        capture_output=True, timeout=900,
    )
    tamanho = LARGURA * ALTURA
    n = len(proc.stdout) // tamanho
    if proc.returncode != 0 or n == 0:
        raise ErroFrames("não foi possível ler os quadros do vídeo")
    return np.frombuffer(proc.stdout[: n * tamanho], dtype=np.uint8).reshape(n, ALTURA, LARGURA)


def _extrair_imagem(video: Path, t: float, destino: Path, ffmpeg: str) -> None:
    proc = subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{t:.3f}", "-i", str(video),
         "-frames:v", "1", "-q:v", "3", str(destino)],
        capture_output=True, text=True, timeout=120,
    )
    if proc.returncode != 0 or not destino.exists() or destino.stat().st_size == 0:
        raise ErroFrames(f"não foi possível extrair o frame em {t:.2f}s")


# ---------- análise e seleção (puro: numpy, sem rede nem ffmpeg) ----------

@dataclass
class Analise:
    util: np.ndarray        # bool por amostra
    pequena: np.ndarray     # (n, 16, 16) float32
    dif_anterior: np.ndarray  # diferença média para a amostra anterior


def analisar(amostras: np.ndarray, p: ParametrosFrames) -> Analise:
    f = amostras.astype(np.float32)
    n = len(f)
    luma = f.mean(axis=(1, 2))
    desvio = f.std(axis=(1, 2))
    lap = 4 * f[:, 1:-1, 1:-1] - f[:, :-2, 1:-1] - f[:, 2:, 1:-1] - f[:, 1:-1, :-2] - f[:, 1:-1, 2:]
    nitidez = lap.var(axis=(1, 2))
    escuro = luma < p.luma_minima
    # Quadro uniforme (sem textura) não é "borrado": cor sólida legítima (slide, fundo) é mantida.
    borrado = (nitidez < p.nitidez_minima) & (desvio > 12)
    util = ~(escuro | borrado)
    if not util.any():  # tudo descartado: melhor devolver algo do que nada
        util = np.ones(n, dtype=bool)
    pequena = f.reshape(n, 16, ALTURA // 16, 16, LARGURA // 16).mean(axis=(2, 4))
    dif = np.full(n, 255.0, dtype=np.float32)
    if n > 1:
        dif[1:] = np.abs(pequena[1:] - pequena[:-1]).mean(axis=(1, 2))
    return Analise(util=util, pequena=pequena, dif_anterior=dif)


def selecionar_indices(n: int, fps: float, d: float, cenas_s: list[float],
                       a: Analise, p: ParametrosFrames) -> list[int]:
    """Índices de amostra escolhidos, em ordem de tempo. Regras 1 a 6 do SPEC, seção 6."""
    t_de = lambda k: k / fps
    util = np.flatnonzero(a.util)
    primeiro, ultimo = int(util[0]), int(util[-1])
    util_set = set(util.tolist())

    # 1. candidatos: primeiro frame útil + cada mudança de cena (na primeira amostra útil a partir do corte)
    cand = {primeiro}
    passos_de_folga = max(1, round(fps))  # procura até ~1 s depois do corte (transição borrada)
    for t in cenas_s:
        k = min(n - 1, math.ceil(t * fps - 1e-9))
        for j in range(k, min(n, k + passos_de_folga + 1)):
            if j in util_set:
                cand.add(j)
                break

    # 3. dedup por miniatura 16x16 em tons de cinza, em ordem de tempo
    mantidos: list[int] = []
    for k in sorted(cand):
        if all(np.abs(a.pequena[k] - a.pequena[m]).mean() >= p.dedup_diferenca for m in mantidos):
            mantidos.append(k)

    # 4. poucos candidatos: completa com amostragem uniforme no tempo
    escolhidos = set(mantidos)
    if len(escolhidos) < p.minimo_candidatos:
        for j in range(p.minimo_candidatos):
            alvo = (j + 0.5) * d / p.minimo_candidatos * fps
            k = int(util[np.abs(util - alvo).argmin()])
            escolhidos.add(k)
            if len(escolhidos) >= p.minimo_candidatos:
                break

    # 5. teto: reduz por amostragem uniforme entre os candidatos
    ordem = sorted(escolhidos)
    if len(ordem) > p.teto:
        pos = np.unique(np.linspace(0, len(ordem) - 1, p.teto).round().astype(int))
        ordem = [ordem[i] for i in pos]
    escolhidos = set(ordem)

    # 6. cobertura: primeiro e último frame útil, e o mínimo por terço
    escolhidos.update({primeiro, ultimo})
    for terco in ("comeco", "meio", "fim"):
        disponiveis = [k for k in util.tolist() if marcador(t_de(k), d) == terco]
        while sum(marcador(t_de(k), d) == terco for k in escolhidos) < p.minimo_por_terco:
            livres = [k for k in disponiveis if k not in escolhidos]
            if not livres:
                break
            lim_ini = {"comeco": 0.0, "meio": d / 3, "fim": 2 * d / 3}[terco]
            lim_fim = {"comeco": d / 3, "meio": 2 * d / 3, "fim": d}[terco]
            pontos = sorted([lim_ini] + [t_de(k) for k in escolhidos if marcador(t_de(k), d) == terco] + [lim_fim])
            vazio = max(range(len(pontos) - 1), key=lambda i: (pontos[i + 1] - pontos[i], -i))
            alvo = (pontos[vazio] + pontos[vazio + 1]) / 2
            estaveis = [k for k in livres if a.dif_anterior[k] <= p.diferenca_estavel] or livres
            escolhidos.add(min(estaveis, key=lambda k: (abs(t_de(k) - alvo), k)))

    # a cobertura pode passar do teto: tira o frame mais "apertado" que não seja necessário
    while len(escolhidos) > p.teto:
        ordem = sorted(escolhidos)
        contagem = {t: sum(marcador(t_de(k), d) == t for k in ordem) for t in ("comeco", "meio", "fim")}
        removiveis = []
        for i, k in enumerate(ordem):
            if k in (primeiro, ultimo) or contagem[marcador(t_de(k), d)] <= p.minimo_por_terco:
                continue
            vizinhos = [abs(ordem[i] - ordem[j]) for j in (i - 1, i + 1) if 0 <= j < len(ordem)]
            removiveis.append((min(vizinhos), k))
        if not removiveis:
            break
        escolhidos.discard(min(removiveis)[1])
    return sorted(escolhidos)


# ---------- API ----------

def selecionar_frames(video: Path, pasta_saida: Path, duracao_s: float | None = None,
                      params: ParametrosFrames | None = None, ffmpeg: str | None = None) -> list[dict]:
    video, pasta_saida = Path(video), Path(pasta_saida)
    params = params or ParametrosFrames.do_ambiente()
    if not video.is_file():
        raise ErroFrames(f"arquivo não encontrado: {video.name}")
    exe = midia.localizar_ffmpeg(ffmpeg)
    d = duracao_s or midia.duracao_video(video, exe)
    if not d or d <= 0:
        raise ErroFrames("não foi possível ler a duração do vídeo")
    fps = min(params.amostras_por_s, params.max_amostras / d)
    with TravaDeTrabalho():
        cenas = _pontuacoes_de_cena(video, params.limiar_cena, exe)
        amostras = _miniaturas(video, fps, exe)
        indices = selecionar_indices(len(amostras), fps, d, cenas, analisar(amostras, params), params)
        pasta_saida.mkdir(parents=True, exist_ok=True)
        frames = []
        for ordem, k in enumerate(indices, start=1):
            t = round(min(k / fps, max(0.0, d - 0.05)), 2)
            arquivo = pasta_saida / f"{ordem:02d}.jpg"
            _extrair_imagem(video, t, arquivo, exe)
            frames.append({"ordem": ordem, "arquivo": arquivo, "segundo": t, "marcador": marcador(t, d)})
    return frames


def folha_de_contato(frames: list[dict], destino: Path, colunas: int = 4, largura: int = 320) -> Path:
    """Grade com as imagens escolhidas e a legenda `ordem · segundo · marcador` (exige Pillow)."""
    from PIL import Image, ImageDraw, ImageFont

    miniaturas = []
    for f in frames:
        im = Image.open(f["arquivo"]).convert("RGB")
        im.thumbnail((largura, largura))
        miniaturas.append((im, f))
    if not miniaturas:
        raise ErroFrames("nenhum frame para a folha de contato")
    altura = max(im.height for im, _ in miniaturas)
    linhas = math.ceil(len(miniaturas) / colunas)
    legenda = 26
    folha = Image.new("RGB", (colunas * largura, linhas * (altura + legenda)), "white")
    desenho = ImageDraw.Draw(folha)
    fonte = ImageFont.load_default(size=16)
    for i, (im, f) in enumerate(miniaturas):
        x, y = (i % colunas) * largura, (i // colunas) * (altura + legenda)
        folha.paste(im, (x, y + legenda))
        desenho.text((x + 4, y + 4), f"{f['ordem']} · {f['segundo']:.1f}s · {f['marcador']}", fill="black", font=fonte)
    folha.save(destino, quality=88)
    return destino


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m scrapagentes.frames")
    p.add_argument("video", type=Path)
    p.add_argument("--saida", type=Path, default=Path("frames_saida"))
    p.add_argument("--folha", type=Path, default=None, help="grava a folha de contato (exige Pillow)")
    args = p.parse_args(argv)
    try:
        t0 = time.monotonic()
        frames = selecionar_frames(args.video, args.saida)
        gasto = time.monotonic() - t0
        if args.folha:
            folha_de_contato(frames, args.folha)
    except (ErroFrames, RuntimeError) as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 1
    for f in frames:
        print(f"{f['ordem']:2d}  {f['segundo']:7.2f}s  {f['marcador']:6s}  {f['arquivo']}")
    d = midia.duracao_video(args.video)
    print(f"\n{len(frames)} frames, tempo={gasto:.1f}s, duracao={d and round(d, 1)}s"
          + (f", tempo/duracao={gasto / d:.2f}x" if d else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
