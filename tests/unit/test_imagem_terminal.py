import shutil
import subprocess

import pytest

from omarchy_manager.services import imagem, terminal_grafico
from omarchy_manager.services.terminal_grafico import Capacidades, interpretar_resposta

tem_magick = pytest.mark.skipif(shutil.which("magick") is None, reason="ImageMagick ausente")


@pytest.fixture(autouse=True)
def _limpa(monkeypatch):
    monkeypatch.delenv("OMARCHY_MANAGER_IMAGEM", raising=False)
    monkeypatch.setattr(terminal_grafico, "_celula_por_ioctl", lambda: (0, 0))
    yield
    terminal_grafico.definir(None)


def test_interpretar_resposta():
    assert interpretar_resposta(b"\x1b[6;20;10t\x1b[?62;4;22c") == (True, False, 10, 20, True)  # foot
    assert interpretar_resposta(b"\x1b_Gi=31;OK\x1b\\\x1b[6;34;17t\x1b[?62;c") == (False, True, 17, 34, True)  # kitty
    assert interpretar_resposta(b"\x1b_Gi=31;ENOTSUPPORTED\x1b\\\x1b[?1;2c") == (False, False, 0, 0, True)
    assert interpretar_resposta(b"\x1b[?64;14;24c")[0] is False  # 14 e 24 não são o atributo 4
    assert interpretar_resposta(b"") == (False, False, 0, 0, False)


def test_protocolo_e_motivo(monkeypatch):
    monkeypatch.setenv("TERM_PROGRAM", "herdr")
    assert terminal_grafico.protocolo() is None and "não foi consultado" in terminal_grafico.motivo_blocos()
    terminal_grafico.definir(Capacidades(consultado=True))
    assert "não respondeu" in terminal_grafico.motivo_blocos()
    terminal_grafico.definir(Capacidades(consultado=True, respondeu=True))
    assert "herdr" in terminal_grafico.motivo_blocos() and "Sixel" in terminal_grafico.motivo_blocos()
    terminal_grafico.definir(Capacidades(sixel=True, consultado=True, respondeu=True))
    assert terminal_grafico.protocolo() is None and "tamanho da célula" in terminal_grafico.motivo_blocos()
    terminal_grafico.definir(Capacidades(sixel=True, cel_l=10, cel_a=20, consultado=True, respondeu=True))
    assert terminal_grafico.protocolo() == "sixel" and terminal_grafico.motivo_blocos() == ""
    terminal_grafico.definir(Capacidades(sixel=True, kitty=True, cel_l=10, cel_a=20, consultado=True, respondeu=True))
    assert terminal_grafico.protocolo() == "kitty"
    monkeypatch.setenv("OMARCHY_MANAGER_IMAGEM", "blocos")
    assert terminal_grafico.protocolo() is None and "forçado" in terminal_grafico.motivo_blocos()


@tem_magick
def test_intermediario_sixel_e_kitty(tmp_path):
    img = tmp_path / "fundo.png"
    subprocess.run(["magick", "-size", "640x360", "gradient:#ff0000-#0000ff", str(img)], check=True)
    cache = tmp_path / "cache"
    inter = imagem.intermediario(img, cache)
    assert inter is not None and inter.suffix == ".jpg" and inter.parent == cache
    assert imagem.intermediario(img, cache) == inter and len(list(cache.iterdir())) == 1  # reaproveita

    dados, larg, alt = imagem.sixel(inter, 400, 203)
    assert dados.startswith("\x1bP") and dados.endswith("\x1b\\")
    assert larg <= 400 and alt <= 198 and abs(larg / alt - 16 / 9) < 0.1  # cabe na caixa, proporção mantida

    seq, larg, alt = imagem.kitty(inter, 400, 200, 7)
    assert seq.startswith("\x1b_Ga=T,f=100,i=7,q=2,C=1,z=-1,m=") and seq.endswith("\x1b\\")
    assert (larg, alt) == (356, 200)
    assert imagem.kitty_apagar(7) == "\x1b_Ga=d,d=I,i=7,q=2\x1b\\"
    assert imagem.sixel(inter, 4, 4) is None


def test_intermediario_de_arquivo_inexistente(tmp_path):
    assert imagem.intermediario(tmp_path / "nao-existe.png", tmp_path / "c") is None


@tem_magick
async def test_widget_emite_sixel_so_quando_cabe_inteiro(tmp_path, monkeypatch):
    from textual.app import App, ComposeResult
    from textual.geometry import Region
    from textual.widgets import Static

    from omarchy_manager.ui.imagem import ImagemTerminal

    monkeypatch.setattr(imagem, "pasta_cache", lambda: tmp_path / "cache")
    img = tmp_path / "fundo.png"
    subprocess.run(["magick", "-size", "640x360", "xc:#336699", str(img)], check=True)
    terminal_grafico.definir(Capacidades(sixel=True, cel_l=10, cel_a=20, consultado=True, respondeu=True))

    class Caixa(App):
        def compose(self) -> ComposeResult:
            yield Static("titulo")
            yield ImagemTerminal(id="foto")

    app = Caixa()
    async with app.run_test(size=(60, 20)) as pilot:
        foto = app.query_one(ImagemTerminal)
        foto.mostrar(img)
        await pilot.pause(0.3)
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert foto._pronto is not None and foto._pronto[3] == "sixel"
        inteiro = Region(0, 0, foto.size.width, foto.size.height)
        texto = "".join(s.text for linha in foto.render_lines(inteiro) for s in linha)
        assert "\x1bP" in texto and f"\x1b[{foto.region.y + 1};" in texto  # posiciona no topo do widget
        parcial = "".join(s.text for linha in foto.render_lines(Region(0, 0, foto.size.width, 3)) for s in linha)
        assert "\x1bP" not in parcial
        # outro tamanho: a imagem antiga não pode sair no espaço novo
        await pilot.resize_terminal(40, 12)
        novo = Region(0, 0, foto.size.width, foto.size.height)
        assert "\x1bP" not in "".join(s.text for linha in foto.render_lines(novo) for s in linha) or foto._chave[1:3] == (foto.size.width, foto.size.height)
        foto.mostrar(None)
        await pilot.pause(0.3)
        assert "\x1bP" not in "".join(s.text for linha in foto.render_lines(Region(0, 0, foto.size.width, foto.size.height)) for s in linha)
