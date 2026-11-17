from omarchy_manager.services import arquivos, caminhos, fundo_livre, prompt_starship, terminal_cfg
from omarchy_manager.services.terminal_cfg import ConfigTerminal

FOOT = """[main]
include=~/.local/state/omarchy/toggles/foot.ini
font=JetBrainsMono Nerd Font:size=8
pad=14x14

[cursor]
style=block
blink=no
"""


def test_definir_ini_troca_cria_e_preserva():
    t = terminal_cfg.definir_ini(FOOT, "main", "pad", "4x4")
    assert terminal_cfg.ler_ini(t, "main", "pad") == "4x4"
    assert "include=~/.local/state/omarchy/toggles/foot.ini" in t
    t = terminal_cfg.definir_ini(t, "cursor", "color", "abc")
    assert t.index("color=abc") < t.index("blink") + 20 and terminal_cfg.ler_ini(t, "cursor", "color") == "abc"
    t = terminal_cfg.definir_ini(t, "colors-dark", "alpha", "0.8")
    assert t.rstrip().endswith("[colors-dark]\nalpha=0.8")


def test_gravar_e_ler_foot_com_backup(tmp_path, monkeypatch):
    monkeypatch.setattr(caminhos, "BACKUPS_DIR", tmp_path / "bk")
    arq = tmp_path / "foot.ini"
    arq.write_text(FOOT)
    cfg = ConfigTerminal(opacidade=80, fonte="Fira Code", tamanho=11, margem=6, cursor="beam", piscar=True, historico=500)
    assert terminal_cfg.gravar(cfg, arq) is not None
    lido = terminal_cfg.ler(arq)
    assert (lido.opacidade, lido.fonte, lido.tamanho, lido.margem, lido.cursor, lido.piscar, lido.historico) == (80, "Fira Code", 11.0, 6, "beam", True, 500)
    assert arquivos.restaurar_ultimo(arq) is not None
    assert terminal_cfg.ler(arq).margem == 14


def test_validar_limita_valores():
    v = terminal_cfg.validar(ConfigTerminal(opacidade=0, tamanho=500, margem=-3, cursor="x", fonte="a:b=c"))
    assert (v.opacidade, v.tamanho, v.margem, v.cursor, v.fonte) == (10, 48.0, 0, "block", "abc")


def test_preset_powerline_tem_pilulas_e_marca():
    assert "preset powerline" in prompt_starship.PRESET_POWERLINE[:120]
    assert prompt_starship.CAP_E in prompt_starship.PRESET_POWERLINE
    assert "${count}" in prompt_starship.PRESET_POWERLINE


def test_listar_fundos_respeita_extensao_e_profundidade(tmp_path):
    (tmp_path / "a" / "b" / "c" / "d").mkdir(parents=True)
    for rel in ("um.png", "a/dois.JPG", "a/b/tres.webp", "a/b/c/quatro.png", "a/b/c/d/fundo.png", "nota.txt"):
        (tmp_path / rel).write_bytes(b"x")
    nomes = [p.name for p in fundo_livre.listar([tmp_path])]
    assert nomes == ["um.png", "dois.JPG", "tres.webp", "quatro.png"]
