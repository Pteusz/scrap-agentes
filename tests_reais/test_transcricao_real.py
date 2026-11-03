"""Transcrição com o modelo de verdade (baixa o modelo na primeira vez; usa CPU da VPS).

    SCRAPAGENTES_TESTES_REAIS=1 .venv/bin/python -m pytest tests_reais/test_transcricao_real.py -m real -p no:cacheprovider

Modelo pelo ambiente: SCRAPAGENTES_WHISPER_MODELO (padrão small).
"""
import os
from pathlib import Path

import pytest

from scrapagentes import transcricao
from scrapagentes.transcricao import wer

pytestmark = [
    pytest.mark.real,
    pytest.mark.skipif(os.environ.get("SCRAPAGENTES_TESTES_REAIS") != "1", reason="defina SCRAPAGENTES_TESTES_REAIS=1"),
]
FALA = Path("tests/fixtures/fala_pt.mp4")
TEXTO = Path("tests/fixtures/fala_pt.txt")


def _exige_fala():
    if not FALA.exists() or not TEXTO.exists():
        pytest.skip("fixtures do Mateus ausentes em tests/fixtures (não versionadas)")


def test_video_sem_fala_devolve_lista_vazia(midias):
    assert transcricao.transcrever(midias["video"]) == []


def test_fala_em_portugues():
    _exige_fala()
    t = transcricao.transcrever(FALA)
    assert t, "esperava trechos"
    assert all(a["fim_s"] <= b["inicio_s"] for a, b in zip(t, t[1:]))
    assert t[-1]["fim_s"] <= 70
    assert wer(TEXTO.read_text(encoding="utf-8"), " ".join(x["texto"] for x in t)) < 0.30


def test_deterministico():
    _exige_fala()
    assert transcricao.transcrever(FALA) == transcricao.transcrever(FALA)
