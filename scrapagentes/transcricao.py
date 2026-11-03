"""Transcrição de vídeo ou áudio em trechos com minutagem. Independe de qualquer rede social.

Entra um arquivo; sai uma lista ordenada de {inicio_s, fim_s, texto} (vazia se não houver fala).
Usa faster-whisper em CPU com int8 e VAD ligado. Um trabalho por vez (trava no processo e entre
processos). Configuração por ambiente: SCRAPAGENTES_WHISPER_MODELO (padrão `small`),
SCRAPAGENTES_IDIOMA (padrão `pt`).

Uso: python -m scrapagentes.transcricao <arquivo> [--modelo small] [--referencia texto.txt]
Com --referencia imprime também o WER e o tempo de processamento sobre a duração do áudio.
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
from pathlib import Path

from scrapagentes import midia

MODELO_PADRAO = "small"
IDIOMA_PADRAO = "pt"

_trava_processo = threading.Lock()
_modelos: dict[str, object] = {}


class ErroTranscricao(Exception):
    pass


class TravaDeTrabalho:
    """Um trabalho pesado por vez: trava entre threads e, onde houver `fcntl`, entre processos."""

    def __init__(self, caminho: Path | None = None):
        self._caminho = caminho or Path(tempfile.gettempdir()) / "scrapagentes-transcricao.lock"
        self._arquivo = None

    def __enter__(self):
        _trava_processo.acquire()
        try:
            import fcntl

            self._arquivo = open(self._caminho, "a")
            fcntl.flock(self._arquivo, fcntl.LOCK_EX)
        except ImportError:  # sem fcntl (Windows): fica só a trava do processo
            self._arquivo = None
        except BaseException:
            _trava_processo.release()
            raise
        return self

    def __exit__(self, *exc):
        try:
            if self._arquivo is not None:
                self._arquivo.close()  # fechar libera o flock
        finally:
            _trava_processo.release()


def extrair_audio(arquivo: Path, destino: Path, ffmpeg: str | None = None) -> Path:
    """WAV 16 kHz, mono. Vídeo sem faixa de áudio vira erro claro, não trecho vazio."""
    proc = subprocess.run(
        [midia.localizar_ffmpeg(ffmpeg), "-hide_banner", "-loglevel", "error", "-y",
         "-i", str(arquivo), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(destino)],
        capture_output=True, text=True, timeout=600,
    )
    if proc.returncode != 0 or not destino.exists() or destino.stat().st_size <= 44:
        raise ErroTranscricao(f"não foi possível extrair áudio: {proc.stderr.strip()[-200:] or 'sem faixa de áudio'}")
    return destino


def normalizar_trechos(brutos, duracao_s: float | None) -> list[dict]:
    """Ordena, descarta vazios, corta no fim da duração e remove sobreposição."""
    trechos = []
    for ini, fim, texto in sorted(brutos, key=lambda t: (t[0], t[1])):
        texto = " ".join((texto or "").split())
        if not texto:
            continue
        ini = max(0.0, float(ini))
        fim = float(fim)
        if duracao_s is not None:
            ini, fim = min(ini, duracao_s), min(fim, duracao_s)
        if trechos:
            ini = max(ini, trechos[-1]["fim_s"])
        if fim <= ini:
            continue
        trechos.append({"inicio_s": round(ini, 2), "fim_s": round(fim, 2), "texto": texto})
    return trechos


def _ler_wav(caminho: Path):
    """WAV 16 kHz mono -> float32 em [-1, 1]. Evita depender do decodificador interno do faster-whisper."""
    import wave

    import numpy as np

    with wave.open(str(caminho), "rb") as w:
        if (w.getnchannels(), w.getframerate(), w.getsampwidth()) != (1, 16000, 2):
            raise ErroTranscricao("o áudio extraído não está em 16 kHz mono de 16 bits")
        bruto = w.readframes(w.getnframes())
    return np.frombuffer(bruto, dtype=np.int16).astype(np.float32) / 32768.0


def _carregar_modelo(nome: str):
    if nome not in _modelos:
        from faster_whisper import WhisperModel

        _modelos[nome] = WhisperModel(nome, device="cpu", compute_type="int8", cpu_threads=4)
    return _modelos[nome]


def transcrever(arquivo: Path, modelo: str | None = None, idioma: str | None = None,
                ffmpeg: str | None = None) -> list[dict]:
    arquivo = Path(arquivo)
    if not arquivo.is_file():
        raise ErroTranscricao(f"arquivo não encontrado: {arquivo.name}")
    modelo = modelo or os.environ.get("SCRAPAGENTES_WHISPER_MODELO", MODELO_PADRAO)
    idioma = idioma or os.environ.get("SCRAPAGENTES_IDIOMA", IDIOMA_PADRAO)
    with TravaDeTrabalho():
        with tempfile.TemporaryDirectory(prefix="scrapagentes-audio-") as pasta:
            wav = extrair_audio(arquivo, Path(pasta) / "audio.wav", ffmpeg)
            duracao = midia.duracao_video(wav, ffmpeg)
            segmentos, _ = _carregar_modelo(modelo).transcribe(
                _ler_wav(wav), language=idioma, vad_filter=True, temperature=0.0,
                condition_on_previous_text=False,
            )
            brutos = [(s.start, s.end, s.text) for s in segmentos]
    return normalizar_trechos(brutos, duracao)


# ---------- avaliação ----------

def _palavras(texto: str) -> list[str]:
    texto = unicodedata.normalize("NFKC", texto).lower()
    texto = re.sub(r"[^\w\s]", " ", texto)
    return texto.split()


def wer(referencia: str, hipotese: str) -> float:
    """Taxa de erro de palavras (distância de edição sobre palavras / palavras da referência).
    Ignora maiúsculas e pontuação; acentos e algarismos contam como diferença."""
    ref, hip = _palavras(referencia), _palavras(hipotese)
    if not ref:
        raise ValueError("referência vazia")
    anterior = list(range(len(hip) + 1))
    for i, r in enumerate(ref, start=1):
        atual = [i]
        for j, h in enumerate(hip, start=1):
            atual.append(min(anterior[j] + 1, atual[j - 1] + 1, anterior[j - 1] + (r != h)))
        anterior = atual
    return anterior[-1] / len(ref)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m scrapagentes.transcricao")
    p.add_argument("arquivo", type=Path)
    p.add_argument("--modelo", default=None)
    p.add_argument("--idioma", default=None)
    p.add_argument("--referencia", type=Path, default=None, help="texto correto, para calcular o WER")
    args = p.parse_args(argv)
    try:
        t0 = time.monotonic()
        trechos = transcrever(args.arquivo, args.modelo, args.idioma)
        gasto = time.monotonic() - t0
    except ErroTranscricao as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 1
    for t in trechos:
        print(f"[{t['inicio_s']:7.2f} -> {t['fim_s']:7.2f}] {t['texto']}")
    duracao = midia.duracao_video(args.arquivo)
    modelo = args.modelo or os.environ.get("SCRAPAGENTES_WHISPER_MODELO", MODELO_PADRAO)
    print(f"\nmodelo={modelo} trechos={len(trechos)} tempo={gasto:.1f}s duracao={duracao and round(duracao, 1)}s"
          + (f" tempo/duracao={gasto / duracao:.2f}x" if duracao else ""))
    if args.referencia:
        texto = " ".join(t["texto"] for t in trechos)
        print(f"WER={wer(args.referencia.read_text(encoding='utf-8'), texto):.1%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
