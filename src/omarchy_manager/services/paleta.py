"""Leitura do colors.toml do tema e conversão para um tema do Textual."""

from __future__ import annotations

import tomllib
from pathlib import Path

from textual.theme import Theme

from omarchy_manager.models import Paleta
from omarchy_manager.services import caminhos

# Cores ANSI seguras (xterm) usadas quando a chave falta no colors.toml.
FALLBACK_ESCURO = {
    "background": "#000000",
    "foreground": "#e5e5e5",
    "accent": "#5c5cff",
    "muted": "#7f7f7f",
    "red": "#cd0000",
    "green": "#00cd00",
    "yellow": "#cdcd00",
    "blue": "#0000ee",
    "selection": "#4d4d4d",
}
FALLBACK_CLARO = {
    "background": "#ffffff",
    "foreground": "#000000",
    "accent": "#0000ee",
    "muted": "#7f7f7f",
    "red": "#cd0000",
    "green": "#00a000",
    "yellow": "#a08000",
    "blue": "#0000ee",
    "selection": "#c0c0c0",
}
OBRIGATORIAS = tuple(FALLBACK_ESCURO)


def paleta_de_dict(dados: dict) -> Paleta:
    mode = str(dados.get("mode", "dark")).lower()
    fallback = FALLBACK_CLARO if mode == "light" else FALLBACK_ESCURO
    valores: dict[str, str] = {}
    ausentes: list[str] = []
    for chave in OBRIGATORIAS:
        bruto = dados.get(chave)
        if isinstance(bruto, str) and _cor_valida(bruto):
            valores[chave] = bruto
        else:
            valores[chave] = fallback[chave]
            ausentes.append(chave)
    extras = {
        k: v for k, v in dados.items() if k not in OBRIGATORIAS and k != "mode" and isinstance(v, str) and _cor_valida(v)
    }
    return Paleta(mode=mode, extras=extras, ausentes=tuple(ausentes), **valores)


def _cor_valida(texto: str) -> bool:
    t = texto.strip()
    if not t.startswith("#") or len(t) not in (4, 7, 9):
        return False
    try:
        int(t[1:], 16)
    except ValueError:
        return False
    return True


def ler_paleta(arquivo: Path) -> Paleta:
    with open(arquivo, "rb") as fh:
        return paleta_de_dict(tomllib.load(fh))


def paleta_atual() -> Paleta:
    """Paleta do tema ativo; se não houver, a ANSI escura de segurança."""
    arquivo = caminhos.OMARCHY_STATE_CURRENT / "theme" / "colors.toml"
    if arquivo.is_file():
        try:
            return ler_paleta(arquivo)
        except (OSError, tomllib.TOMLDecodeError):
            pass
    return paleta_de_dict({})


def tema_textual(paleta: Paleta, nome: str = "omarchy") -> Theme:
    return Theme(
        name=nome,
        primary=paleta.accent,
        secondary=paleta.blue,
        accent=paleta.accent,
        foreground=paleta.foreground,
        background=paleta.background,
        surface=paleta.extras.get("dark_background", paleta.background),
        panel=paleta.extras.get("lighter_background", paleta.selection),
        success=paleta.green,
        warning=paleta.yellow,
        error=paleta.red,
        dark=paleta.escuro,
        variables={
            "omarchy-muted": paleta.muted,
            "omarchy-selection": paleta.selection,
            "footer-key-foreground": paleta.accent,
        },
    )
