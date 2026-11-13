import pytest

from omarchy_manager.services import terminal_foot, terminal_grafico
from omarchy_manager.services.terminal_grafico import Capacidades


@pytest.fixture(autouse=True)
def _limpa(monkeypatch):
    monkeypatch.setenv("TERM", "xterm-256color")
    yield
    terminal_grafico.definir(None)


def _ini(tmp_path):
    tema = tmp_path / "tema.ini"
    tema.write_text("[colors-dark]\nbackground=0c0b0c\nblur=yes\n")
    usuario = tmp_path / "foot.ini"
    usuario.write_text(f"[main]\ninclude={tema}\nterm=xterm-256color\n\n[colors-dark]\nalpha=0.25  # meu\nalpha-mode=all\n\n[colors-light]\nalpha=0.4\n")
    return usuario, tema


def test_le_alpha_do_usuario_seguindo_include(tmp_path):
    usuario, tema = _ini(tmp_path)
    assert terminal_foot.alpha_do_usuario(True, usuario) == 0.25
    assert terminal_foot.alpha_do_usuario(False, usuario) == 0.4
    tema.write_text("[colors-dark]\nalpha=0.9\n")  # o do usuário vem depois e vence
    assert terminal_foot.alpha_do_usuario(True, usuario) == 0.25
    assert terminal_foot.alpha_do_usuario(True, tmp_path / "nao-existe.ini") is None
    laco = tmp_path / "laco.ini"
    laco.write_text(f"include={laco}\n[colors]\nalpha=0.5\n")
    assert terminal_foot.alpha_do_usuario(True, laco) == 0.5


def test_sequencia_so_no_foot_e_com_alpha(tmp_path):
    usuario, _ = _ini(tmp_path)
    assert terminal_foot.sequencia_alpha("#0c0b0c", True, usuario) == ""  # terminal não identificado
    terminal_grafico.definir(Capacidades(consultado=True, respondeu=True, nome="herdr 0.9.5"))
    assert terminal_foot.sequencia_alpha("#0c0b0c", True, usuario) == ""
    terminal_grafico.definir(Capacidades(consultado=True, respondeu=True, nome="foot(1.28.0)"))
    assert terminal_foot.sequencia_alpha("#0c0b0c", True, usuario) == "\x1b]11;[25]#0c0b0c\x07"
    assert terminal_foot.sequencia_alpha("#eff1f5", False, usuario) == "\x1b]11;[40]#eff1f5\x07"
    assert terminal_foot.sequencia_alpha("vermelho", True, usuario) == ""
    opaco = tmp_path / "opaco.ini"
    opaco.write_text("[colors-dark]\nalpha=1.0\n")
    assert terminal_foot.sequencia_alpha("#0c0b0c", True, opaco) == ""
    assert terminal_foot.sequencia_alpha("#0c0b0c", True, tmp_path / "nada.ini") == ""


def test_xtversion_na_consulta():
    assert b"\x1b[>q" in terminal_grafico.CONSULTA
    m = terminal_grafico._RE_NOME.search(b"\x1bP>|foot(1.28.0)\x1b\\\x1b[?62;4;22c")
    assert m.group(1) == b"foot(1.28.0)"
