import pytest

from omarchy_manager.services.teclas import (
    Combinacao,
    CombinacaoInvalida,
    combinacao_legivel,
    conflitam,
    normalizar,
)


@pytest.mark.parametrize(
    "entrada, esperado",
    [
        ("Super+Shift+q", "SUPER + SHIFT + Q"),
        ("SUPER SHIFT, Q", "SUPER + SHIFT + Q"),
        ("shift + super + q", "SUPER + SHIFT + Q"),
        ("ctrl+alt+Delete", "CTRL + ALT + DELETE"),
        ("super + code:59", "SUPER + code:59"),
        ("SUPER + Enter", "SUPER + RETURN"),
        ("win + space", "SUPER + SPACE"),
        ("XF86AudioMute", "XF86AUDIOMUTE"),
        ("super + ç", "SUPER + CCEDILLA"),
        ("super + <", "SUPER + LESS"),
    ],
)
def test_normalizacao(entrada, esperado):
    assert normalizar(entrada).canonica == esperado


def test_modmask_calculado():
    c = normalizar("super + ctrl + alt + shift + f")
    assert c.modmask == 64 + 4 + 8 + 1


@pytest.mark.parametrize("ruim", ["", "super", "super + a + b", "super + code:xx"])
def test_invalidas(ruim):
    with pytest.raises(CombinacaoInvalida):
        normalizar(ruim)


def test_conflito_por_nome():
    assert conflitam(normalizar("SUPER + Q"), Combinacao(64, "q"))
    assert not conflitam(normalizar("SUPER + Q"), Combinacao(65, "Q"))


def test_conflito_por_keycode():
    # code:59 no ABNT2 é a vírgula; "SUPER + SHIFT + COMMA" é o mesmo atalho.
    assert conflitam(normalizar("SUPER + SHIFT + code:59"), normalizar("SUPER + SHIFT + COMMA"))
    # keycode informado pelo hyprctl junto com key vazia.
    assert conflitam(Combinacao(64, "", 60), normalizar("SUPER + PERIOD"))
    assert not conflitam(Combinacao(64, "", 60), normalizar("SUPER + COMMA"))


def test_legivel_com_keycode_sem_nome():
    assert combinacao_legivel(68, "", 19) == "SUPER + CTRL + code:19"
    assert combinacao_legivel(0, "Print") == "PRINT"
