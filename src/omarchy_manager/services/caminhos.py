"""Caminhos do usuário (seção 4 do plano) e a trava de /usr/share/omarchy/."""

from __future__ import annotations

import os
from pathlib import Path


def _xdg(variavel: str, padrao: str) -> Path:
    return Path(os.environ.get(variavel) or Path.home() / padrao)


CONFIG_DIR = _xdg("XDG_CONFIG_HOME", ".config") / "omarchy-manager"
STATE_DIR = _xdg("XDG_STATE_HOME", ".local/state") / "omarchy-manager"
DATA_DIR = _xdg("XDG_DATA_HOME", ".local/share") / "omarchy-manager"

CONFIG_TOML = CONFIG_DIR / "config.toml"
PLUGIN_SHORTCUTS_TOML = CONFIG_DIR / "plugin-shortcuts.toml"
BACKUPS_DIR = STATE_DIR / "backups"
LOG_FILE = STATE_DIR / "manager.log"
THEME_WORKSPACES_DIR = DATA_DIR / "theme-workspaces"

HYPR_DIR = _xdg("XDG_CONFIG_HOME", ".config") / "hypr"
HYPR_BINDINGS = HYPR_DIR / "bindings.lua"
HYPR_MANAGER_BINDINGS = HYPR_DIR / "omarchy-manager-bindings.lua"

OMARCHY_CONFIG_DIR = _xdg("XDG_CONFIG_HOME", ".config") / "omarchy"
OMARCHY_USER_THEMES = OMARCHY_CONFIG_DIR / "themes"
OMARCHY_USER_BACKGROUNDS = OMARCHY_CONFIG_DIR / "backgrounds"
OMARCHY_USER_PLUGINS = OMARCHY_CONFIG_DIR / "plugins"
OMARCHY_STATE_CURRENT = _xdg("XDG_STATE_HOME", ".local/state") / "omarchy" / "current"


def omarchy_path() -> Path:
    return Path(os.environ.get("OMARCHY_PATH") or "/usr/share/omarchy")


PROIBIDOS = (Path("/usr/share/omarchy"),)


class CaminhoProibido(PermissionError):
    """Tentativa de escrever dentro de um diretório que o plano proíbe."""


def garantir_gravavel(caminho: Path) -> Path:
    """Resolve o caminho e recusa qualquer um dentro de /usr/share/omarchy/."""
    resolvido = Path(caminho).expanduser().resolve()
    for proibido in PROIBIDOS + (omarchy_path(),):
        try:
            resolvido.relative_to(proibido.resolve())
        except ValueError:
            continue
        raise CaminhoProibido(f"gravação proibida em {proibido}: {resolvido}")
    return resolvido


def preparar_diretorios() -> None:
    for d in (CONFIG_DIR, STATE_DIR, BACKUPS_DIR, DATA_DIR, THEME_WORKSPACES_DIR):
        d.mkdir(parents=True, exist_ok=True)
