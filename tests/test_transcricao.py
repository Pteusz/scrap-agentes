"""Transcrição sem modelo: normalização, WER, extração de áudio e trava. O modelo real fica em tests_reais."""
import threading
import time

import pytest

from scrapagentes import transcricao
from scrapagentes.transcricao import ErroTranscricao, TravaDeTrabalho, normalizar_trechos, wer


def test_normaliza_ordena_corta_e_remove_sobreposicao():
    brutos = [(5.0, 8.0, " segundo "), (0.0, 5.5, "primeiro"), (9.0, 9.0, "vazio de tempo"),
              (8.0, 20.0, "terceiro"), (3.0, 4.0, "   ")]
    t = normalizar_trechos(brutos, duracao_s=12.0)
    assert [x["texto"] for x in t] == ["primeiro", "segundo", "terceiro"]
    assert t[0] == {"inicio_s": 0.0, "fim_s": 5.5, "texto": "primeiro"}
    assert t[1]["inicio_s"] == 5.5  # não sobrepõe o anterior
    assert t[-1]["fim_s"] == 12.0   # não passa da duração
    assert all(a["fim_s"] <= b["inicio_s"] for a, b in zip(t, t[1:]))


def test_sem_fala_devolve_lista_vazia():
    assert normalizar_trechos([], 10.0) == []
    assert normalizar_trechos([(1, 2, "  ")], 10.0) == []


def test_wer():
    assert wer("a casa é azul", "A casa é azul!") == 0
    assert wer("a casa é azul", "a casa azul") == pytest.approx(0.25)   # uma exclusão
    assert wer("um dois", "um tres quatro") == pytest.approx(1.0)       # 1 troca + 1 inserção
    with pytest.raises(ValueError):
        wer("", "x")


def test_extrair_audio_16k_mono(midias, tmp_path):
    wav = transcricao.extrair_audio(midias["video"], tmp_path / "a.wav")
    dados = wav.read_bytes()
    assert dados[:4] == b"RIFF" and dados[8:12] == b"WAVE"
    assert int.from_bytes(dados[22:24], "little") == 1       # mono
    assert int.from_bytes(dados[24:28], "little") == 16000   # 16 kHz


def test_arquivo_inexistente_ou_sem_audio(tmp_path):
    with pytest.raises(ErroTranscricao):
        transcricao.transcrever(tmp_path / "nao_existe.mp4")
    vazio = tmp_path / "lixo.mp4"
    vazio.write_bytes(b"isto nao e um video")
    with pytest.raises(ErroTranscricao):
        transcricao.extrair_audio(vazio, tmp_path / "a.wav")


def test_um_trabalho_por_vez(tmp_path):
    ativos, pico = [0], [0]
    controle = threading.Lock()

    def trabalho():
        with TravaDeTrabalho(tmp_path / "t.lock"):
            with controle:
                ativos[0] += 1
                pico[0] = max(pico[0], ativos[0])
            time.sleep(0.15)
            with controle:
                ativos[0] -= 1

    ths = [threading.Thread(target=trabalho) for _ in range(4)]
    [t.start() for t in ths]
    [t.join() for t in ths]
    assert pico[0] == 1


def test_trava_entre_processos(tmp_path):
    fcntl = pytest.importorskip("fcntl")
    import subprocess
    import sys
    lock = tmp_path / "p.lock"
    codigo = (
        "import sys,time;from pathlib import Path;"
        "from scrapagentes.transcricao import TravaDeTrabalho;"
        "t=TravaDeTrabalho(Path(sys.argv[1]));t.__enter__();print('preso',flush=True);time.sleep(1.5)"
    )
    filho = subprocess.Popen([sys.executable, "-c", codigo, str(lock)], stdout=subprocess.PIPE, text=True)
    assert filho.stdout.readline().strip() == "preso"
    t0 = time.monotonic()
    with TravaDeTrabalho(lock):
        esperou = time.monotonic() - t0
    filho.wait()
    assert esperou >= 0.8
