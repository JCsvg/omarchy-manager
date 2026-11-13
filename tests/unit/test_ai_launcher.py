import json

import pytest

from omarchy_manager.services import caminhos
from omarchy_manager.services.ai_launcher import ADAPTADORES, AiLauncher, slugificar


def _which_de(tmp_path, nomes):
    pasta = tmp_path / "bin"
    pasta.mkdir(exist_ok=True)
    for n in nomes:
        (pasta / n).write_text("#!/bin/sh\n")
        (pasta / n).chmod(0o755)
    return lambda nome: str(pasta / nome) if (pasta / nome).exists() else None


def test_slug():
    assert slugificar("Noite de Verão!") == "noite-de-ver-o"
    assert slugificar("  ") == "novo-tema"


def test_detecta_so_as_instaladas(tmp_path, monkeypatch):
    monkeypatch.delenv("TERMINAL", raising=False)
    which = _which_de(tmp_path, ["claude", "opencode", "foot"])
    ia = AiLauncher(which=which, abrir=lambda *a, **k: None, workspaces=tmp_path / "ws")
    assert [d.adaptador.id for d in ia.disponiveis()] == ["claude", "opencode"]
    assert ia.terminal()[1].endswith("/foot")


def test_terminal_respeita_env(tmp_path, monkeypatch):
    which = _which_de(tmp_path, ["foot", "kitty"])
    monkeypatch.setenv("TERMINAL", "kitty")
    ia = AiLauncher(which=which, abrir=lambda *a, **k: None, workspaces=tmp_path / "ws")
    assert ia.terminal()[0].executavel == "kitty"


def test_prefere_xdg_terminal_exec(tmp_path, monkeypatch):
    monkeypatch.delenv("TERMINAL", raising=False)
    which = _which_de(tmp_path, ["foot", "xdg-terminal-exec"])
    ia = AiLauncher(which=which, abrir=lambda *a, **k: None, workspaces=tmp_path / "ws")
    adaptador, caminho = ia.terminal()
    assert adaptador.executavel == "xdg-terminal-exec"
    argv = adaptador.argumentos(caminho, tmp_path / "ws" / "x", ["claude", "oi"])
    assert argv[1] == f"--dir={tmp_path / 'ws' / 'x'}" and argv[2:] == ["claude", "oi"]


@pytest.mark.parametrize("cli", [a.executavel for a in ADAPTADORES])
def test_abre_cada_adaptador_com_executavel_falso(tmp_path, monkeypatch, cli):
    monkeypatch.delenv("TERMINAL", raising=False)
    monkeypatch.setattr(caminhos, "PROIBIDOS", (tmp_path / "proibido",))
    which = _which_de(tmp_path, [cli, "foot"])
    chamadas = []
    ia = AiLauncher(which=which, abrir=lambda argv, cwd=None: chamadas.append((argv, cwd)), workspaces=tmp_path / "ws")
    base = tmp_path / "tokyo-night"
    (base / "backgrounds").mkdir(parents=True)
    (base / "colors.toml").write_text('mode = "dark"\n')
    (base / ".git").mkdir()

    disponivel = ia.disponiveis()[0]
    argv = ia.abrir(disponivel, "Meu Tema", base)

    assert chamadas and chamadas[0][0] == argv
    assert all(isinstance(x, str) for x in argv)
    assert argv[0].endswith("/foot") and argv[1] == f"--working-directory={tmp_path / 'ws' / 'meu-tema'}"
    assert argv[3].endswith("/" + cli)
    if cli == "claude":
        assert argv[4:6] == ["--append-system-prompt-file", "AGENTE-CRIADOR-DE-TEMAS.md"]
    if cli != "copilot":
        assert any("AGENTE-CRIADOR-DE-TEMAS.md" in x and "Meu Tema" in x for x in argv)
    ws = tmp_path / "ws" / "meu-tema"
    assert (ws / "AGENTE-CRIADOR-DE-TEMAS.md").is_file()
    assert (ws / disponivel.adaptador.arquivo_instrucoes).is_file()
    assert (ws / "base" / "tokyo-night" / "colors.toml").is_file()
    assert not (ws / "base" / "tokyo-night" / ".git").exists()


def test_sem_terminal(tmp_path):
    which = _which_de(tmp_path, ["claude"])
    ia = AiLauncher(which=which, abrir=lambda *a, **k: None, workspaces=tmp_path / "ws")
    with pytest.raises(FileNotFoundError):
        ia.abrir(ia.disponiveis()[0], "x")


def test_workspace_nunca_em_caminho_proibido(tmp_path, monkeypatch):
    monkeypatch.setattr(caminhos, "PROIBIDOS", (tmp_path / "proibido",))
    which = _which_de(tmp_path, ["claude", "foot"])
    ia = AiLauncher(which=which, abrir=lambda *a, **k: None, workspaces=tmp_path / "proibido" / "ws")
    with pytest.raises(caminhos.CaminhoProibido):
        ia.preparar_workspace("x", ADAPTADORES[0])
