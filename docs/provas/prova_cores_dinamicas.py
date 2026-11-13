"""Prova técnica: trocar a paleta do Textual em tempo de execução.

Registra dois temas (um escuro e um claro) a partir de dicionários no formato
do colors.toml do Omarchy e troca entre eles com a aplicação aberta, usando o
Pilot headless. Passa se as variáveis CSS derivadas mudarem após a troca.
"""

import asyncio

from textual.app import App, ComposeResult
from textual.theme import Theme
from textual.widgets import Static

ESCURO = {
    "background": "#1A1B26",
    "foreground": "#A9B1D6",
    "accent": "#9ECE6A",
    "muted": "#414868",
    "red": "#F7768E",
    "green": "#9ECE6A",
    "yellow": "#E0AF68",
    "blue": "#7AA2F7",
}
CLARO = {
    "background": "#eff1f5",
    "foreground": "#4c4f69",
    "accent": "#1e66f5",
    "muted": "#acb0be",
    "red": "#d20f39",
    "green": "#40a02b",
    "yellow": "#df8e1d",
    "blue": "#1e66f5",
}


def tema_de_paleta(nome: str, p: dict, escuro: bool) -> Theme:
    return Theme(
        name=nome,
        primary=p["accent"],
        secondary=p["blue"],
        accent=p["accent"],
        foreground=p["foreground"],
        background=p["background"],
        surface=p["background"],
        panel=p["muted"],
        success=p["green"],
        warning=p["yellow"],
        error=p["red"],
        dark=escuro,
    )


class Prova(App):
    def compose(self) -> ComposeResult:
        yield Static("prova", id="texto")


async def main() -> None:
    app = Prova()
    app.register_theme(tema_de_paleta("omarchy-escuro", ESCURO, True))
    app.register_theme(tema_de_paleta("omarchy-claro", CLARO, False))
    async with app.run_test() as pilot:
        app.theme = "omarchy-escuro"
        await pilot.pause()
        bg1 = app.current_theme.background
        fg1 = app.get_css_variables()["foreground"]
        app.theme = "omarchy-claro"
        await pilot.pause()
        bg2 = app.current_theme.background
        fg2 = app.get_css_variables()["foreground"]
    print("escuro:", bg1, fg1)
    print("claro: ", bg2, fg2)
    assert bg1 != bg2 and fg1 != fg2, "a paleta não mudou"
    print("PROVA CORES: OK")


if __name__ == "__main__":
    asyncio.run(main())
