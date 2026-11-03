"""Seleção de frames com vídeos sintéticos gerados pelo ffmpeg (nenhuma mídia real)."""
import subprocess

import numpy as np
import pytest

from scrapagentes import frames, midia
from scrapagentes.frames import ParametrosFrames, marcador, selecionar_frames

COR_DE_CADA_CENA = ["red", "green", "blue", "yellow", "white", "0x808080"]


def _gerar(destino, entradas, filtro=None):
    cmd = [midia.localizar_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y"]
    for e in entradas:
        cmd += ["-f", "lavfi", "-i", e]
    if filtro:
        cmd += ["-filter_complex", filtro, "-map", "[v]"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast", str(destino)]
    subprocess.run(cmd, check=True, capture_output=True)
    return destino


def _concat(destino, trechos):
    """trechos: lista de (fonte lavfi, duração)."""
    entradas = [f"{f}:s=320x240:r=10:d={d}" for f, d in trechos]
    n = len(entradas)
    filtro = "".join(f"[{i}:v]" for i in range(n)) + f"concat=n={n}:v=1:a=0[v]"
    return _gerar(destino, entradas, filtro)


@pytest.fixture(scope="module")
def pasta(tmp_path_factory):
    return tmp_path_factory.mktemp("frames")


@pytest.fixture(scope="module")
def seis_cenas(pasta):
    return _concat(pasta / "seis.mp4", [(f"color=c={c}", 5) for c in COR_DE_CADA_CENA])


@pytest.fixture(scope="module")
def estatico(pasta):
    return _gerar(pasta / "estatico.mp4",
                  ["color=c=0x336699:s=320x240:r=10:d=30,drawgrid=w=40:h=40:t=2:c=white"])


@pytest.fixture(scope="module")
def comeco_preto(pasta):
    return _concat(pasta / "preto.mp4", [("color=c=black", 4), ("color=c=red", 8), ("color=c=blue", 8),
                                         ("color=c=yellow", 8), ("color=c=white", 2)])


def _segundos(fs):
    return [f["segundo"] for f in fs]


def _terco(fs, d, nome):
    return [f for f in fs if f["marcador"] == nome]


def test_marcador_nas_bordas():
    d = 30.0
    assert marcador(0, d) == "comeco"
    assert marcador(9.99, d) == "comeco"
    assert marcador(10.0, d) == "meio"
    assert marcador(19.99, d) == "meio"
    assert marcador(20.0, d) == "fim"
    assert marcador(30.0, d) == "fim"
    assert marcador(1.0, 3.0) == "meio" and marcador(2.0, 3.0) == "fim"


def test_seis_cenas_um_frame_por_cena_sem_duplicados(seis_cenas, tmp_path):
    fs = selecionar_frames(seis_cenas, tmp_path)
    segs = _segundos(fs)
    assert len(set(segs)) == len(segs)
    for i in range(6):
        assert any(5 * i <= s < 5 * (i + 1) for s in segs), f"cena {i} sem frame: {segs}"
    assert [f["ordem"] for f in fs] == list(range(1, len(fs) + 1))
    assert segs == sorted(segs)
    assert all(f["arquivo"].is_file() and f["arquivo"].stat().st_size > 0 for f in fs)


def test_estatico_cai_na_amostragem_uniforme_e_cobre_os_tres_tercos(estatico, tmp_path):
    fs = selecionar_frames(estatico, tmp_path)
    assert len(fs) >= 8
    for nome in ("comeco", "meio", "fim"):
        assert len(_terco(fs, 30, nome)) >= 2


def test_comeco_preto_nao_escolhe_frame_preto(comeco_preto, tmp_path):
    fs = selecionar_frames(comeco_preto, tmp_path)
    assert fs[0]["segundo"] >= 3.5
    assert all(f["segundo"] >= 3.5 for f in fs)


def test_teto_e_minimo_por_terco(pasta, tmp_path):
    # 60 cenas de 0,5 s: muitos candidatos, o teto de 16 precisa valer sem quebrar a cobertura
    cores = [f"0x{(i * 4 + 20) % 256:02x}{(i * 37) % 256:02x}{(i * 91) % 256:02x}" for i in range(60)]
    video = _concat(pasta / "muitas.mp4", [(f"color=c={c}", 0.5) for c in cores])
    fs = selecionar_frames(video, tmp_path)
    assert len(fs) <= 16
    for nome in ("comeco", "meio", "fim"):
        assert len(_terco(fs, 30, nome)) >= 2


def test_deterministico(seis_cenas, tmp_path):
    a = selecionar_frames(seis_cenas, tmp_path / "a")
    b = selecionar_frames(seis_cenas, tmp_path / "b")
    assert [(f["segundo"], f["marcador"]) for f in a] == [(f["segundo"], f["marcador"]) for f in b]


def test_marcadores_batem_com_a_regra(seis_cenas, tmp_path):
    d = midia.duracao_video(seis_cenas)
    for f in selecionar_frames(seis_cenas, tmp_path):
        assert f["marcador"] == marcador(f["segundo"], d)


def test_video_muito_curto_nao_falha(pasta, tmp_path):
    video = _gerar(pasta / "curto.mp4", ["testsrc=s=320x240:r=10:d=1.5"])
    fs = selecionar_frames(video, tmp_path)
    assert len(fs) >= 1
    assert all(0 <= f["segundo"] <= 1.5 for f in fs)


def test_erros_claros(tmp_path):
    with pytest.raises(frames.ErroFrames):
        selecionar_frames(tmp_path / "nao_existe.mp4", tmp_path / "s")
    lixo = tmp_path / "lixo.mp4"
    lixo.write_bytes(b"isto nao e um video")
    with pytest.raises(frames.ErroFrames):
        selecionar_frames(lixo, tmp_path / "s")


def test_parametros_do_ambiente(monkeypatch):
    monkeypatch.setenv("SCRAPAGENTES_FRAMES_TETO", "12")
    monkeypatch.setenv("SCRAPAGENTES_FRAMES_LIMIAR_CENA", "0.35")
    p = ParametrosFrames.do_ambiente()
    assert p.teto == 12 and p.limiar_cena == 0.35 and p.minimo_por_terco == 2


def test_analise_descarta_preto_e_borrado():
    p = ParametrosFrames()
    h, w = frames.ALTURA, frames.LARGURA
    rng = np.random.default_rng(0)
    nitido = rng.integers(0, 256, (h, w), dtype=np.uint8)
    preto = np.zeros((h, w), dtype=np.uint8)
    degrade = np.tile(np.linspace(40, 215, w, dtype=np.uint8), (h, 1))  # liso, mas com variação: "borrado"
    solido = np.full((h, w), 120, dtype=np.uint8)                        # cor sólida legítima
    util = frames.analisar(np.stack([nitido, preto, degrade, solido]), p).util
    assert util.tolist() == [True, False, False, True]
