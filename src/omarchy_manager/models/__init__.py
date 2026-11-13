"""Modelos de dados do gerenciador. Só dados, sem subprocesso nem I/O."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

Origem = Literal["omarchy", "usuario", "plugin", "gerenciador", "desconhecida"]


@dataclass(frozen=True)
class Plugin:
    id: str
    name: str
    kinds: tuple[str, ...] = ()
    enabled: bool = False
    active: bool = False
    can_disable: bool = True
    first_party: bool = False
    cloned_from: str = ""
    path: Path | None = None
    description: str = ""
    author: str = ""
    version: str = ""
    repository_url: str = ""
    metadados_incompletos: tuple[str, ...] = ()
    nome_original: str = ""
    descricao_original: str = ""

    @property
    def terceiro(self) -> bool:
        return not self.first_party

    @property
    def desinstalavel(self) -> bool:
        """Só plugin de terceiros instalado em ~/.config/omarchy/plugins."""
        return self.terceiro and self.path is not None

    @property
    def tipo_legivel(self) -> str:
        return ", ".join(self.kinds) if self.kinds else "?"


@dataclass(frozen=True)
class Paleta:
    mode: str
    background: str
    foreground: str
    accent: str
    muted: str
    red: str
    green: str
    yellow: str
    blue: str
    selection: str
    extras: dict[str, str] = field(default_factory=dict)
    ausentes: tuple[str, ...] = ()

    @property
    def escuro(self) -> bool:
        return self.mode != "light"


@dataclass(frozen=True)
class Tema:
    slug: str
    nome: str
    path: Path
    do_usuario: bool
    paleta: Paleta | None = None
    fundos: tuple[Path, ...] = ()
    fundo_padrao: Path | None = None
    atual: bool = False


@dataclass(frozen=True)
class Atalho:
    modmask: int
    key: str
    keycode: int = 0
    description: str = ""
    dispatcher: str = ""
    arg: str = ""
    submap: str = ""
    origem: Origem = "desconhecida"
    plugin_id: str = ""
    arquivo: str = ""
    comando: str = ""
    duplicado: bool = False

    @property
    def combinacao(self) -> str:
        from omarchy_manager.services.teclas import combinacao_legivel

        return combinacao_legivel(self.modmask, self.key, self.keycode)
