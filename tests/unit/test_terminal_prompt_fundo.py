from omarchy_manager.services import arquivos, caminhos, fundo_livre, prompt_posh, terminal_cfg
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


def test_prompt_posh_liga_desliga_idempotente(tmp_path, monkeypatch):
    monkeypatch.setattr(caminhos, "BACKUPS_DIR", tmp_path / "bk")
    monkeypatch.setattr(prompt_posh, "binario", lambda: "/x/oh-my-posh")
    rc, tema = tmp_path / ".bashrc", tmp_path / "cfg" / "t.omp.json"
    rc.write_text("alias a=b\n")
    assert prompt_posh.ativar(rc, tema)[0] and prompt_posh.ativo(rc)
    um = rc.read_text()
    assert um.count(prompt_posh.INICIO) == 1 and "alias a=b" in um and str(tema) in um
    assert prompt_posh.ativar(rc, tema)[0] and rc.read_text() == um
    assert tema.exists() and "\ue0b0" in tema.read_text()
    assert prompt_posh.desativar(rc)[0] and not prompt_posh.ativo(rc)
    assert rc.read_text().strip() == "alias a=b"
    assert not prompt_posh.desativar(rc)[0]
    assert (tmp_path / "bk").is_dir()


def test_prompt_posh_sem_binario_nao_altera(tmp_path, monkeypatch):
    monkeypatch.setattr(prompt_posh, "binario", lambda: None)
    rc = tmp_path / ".bashrc"
    assert not prompt_posh.ativar(rc, tmp_path / "t.json")[0] and not rc.exists()


def test_listar_fundos_inclui_subpastas_ate_3_niveis(tmp_path, monkeypatch):
    monkeypatch.setattr(caminhos, "CONFIG_DIR", tmp_path / "cfg")
    (tmp_path / "a" / "b" / "c" / "d").mkdir(parents=True)
    for rel in ("b.png", "x.JPG", "a/dois.webp", "a/b/c/quatro.png", "a/b/c/d/cinco.png", "nota.txt"):
        (tmp_path / rel).write_bytes(b"x")
    assert [p.name for p in fundo_livre.listar(tmp_path)] == ["b.png", "x.JPG", "dois.webp", "quatro.png"]
    assert fundo_livre.listar(None) == []
    assert fundo_livre.pasta_escolhida() is None
    fundo_livre.definir_pasta(tmp_path)
    assert fundo_livre.pasta_escolhida() == tmp_path.resolve()
