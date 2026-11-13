import shutil

import pytest

from omarchy_manager.services.theme_preview import blocos_de_imagem, blocos_de_ppm, ler_ppm, terminal_suporta_sixel


def _ppm(largura, altura, cor):
    return f"P6\n{largura} {altura}\n255\n".encode() + bytes(cor) * (largura * altura)


def test_ler_ppm():
    assert ler_ppm(_ppm(2, 2, (1, 2, 3))) == (2, 2, bytes((1, 2, 3)) * 4)
    assert ler_ppm(b"P3\n1 1\n255\n0 0 0") is None
    assert ler_ppm(b"P6\n2 2\n255\n\x00") is None


def test_blocos():
    linhas = blocos_de_ppm(_ppm(3, 4, (255, 0, 0)))
    assert len(linhas) == 2
    assert linhas[0].count("▀") == 3
    assert "#ff0000 on #ff0000" in linhas[0]


def test_sixel_por_ambiente(monkeypatch):
    monkeypatch.setenv("TERM_PROGRAM", "foot")
    assert terminal_suporta_sixel()
    monkeypatch.setenv("TERM_PROGRAM", "herdr")
    monkeypatch.setenv("TERM", "xterm-256color")
    assert not terminal_suporta_sixel()


@pytest.mark.skipif(shutil.which("magick") is None, reason="ImageMagick ausente")
def test_blocos_de_imagem_real(tmp_path):
    from subprocess import run

    img = tmp_path / "a.png"
    run(["magick", "-size", "20x10", "xc:#336699", str(img)], check=True)
    linhas = blocos_de_imagem(img, largura=10, altura_linhas=3)
    assert linhas is not None and len(linhas) == 3
    assert "#336699" in linhas[0]
