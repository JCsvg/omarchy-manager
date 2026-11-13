from omarchy_manager.services.paleta import FALLBACK_ESCURO, ler_paleta, paleta_de_dict, tema_textual


def test_paleta_escura(fixtures):
    p = ler_paleta(fixtures / "colors_dark.toml")
    assert p.escuro
    assert p.background == "#1A1B26"
    assert p.accent == "#9ECE6A"
    assert p.ausentes == ()
    assert p.extras["dark_background"] == "#13141C"


def test_paleta_clara(fixtures):
    p = ler_paleta(fixtures / "colors_light.toml")
    assert not p.escuro
    assert p.foreground == "#4c4f69"


def test_chave_ausente_usa_ansi(fixtures):
    p = ler_paleta(fixtures / "colors_incompleto.toml")
    assert set(p.ausentes) == {"foreground", "blue", "selection", "yellow"}
    assert p.foreground == FALLBACK_ESCURO["foreground"]
    assert p.yellow == FALLBACK_ESCURO["yellow"]
    assert p.accent == "#ff8800"


def test_dict_vazio_vira_paleta_segura():
    p = paleta_de_dict({})
    assert len(p.ausentes) == 9
    assert p.escuro


def test_tema_textual_usa_as_cores(fixtures):
    p = ler_paleta(fixtures / "colors_light.toml")
    t = tema_textual(p, "teste")
    assert t.name == "teste"
    assert t.dark is False
    assert t.background == "#eff1f5"
    assert t.error == "#d20f39"
    assert t.variables["omarchy-muted"] == "#acb0be"
