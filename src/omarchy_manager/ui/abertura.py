"""Tela de abertura OMARCHY MANAGER, mostrada na primeira abertura de cada boot."""

from __future__ import annotations

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

LETRAS = {
    "O": [" ███ ", "█   █", "█   █", "█   █", " ███ "],
    "M": ["█   █", "██ ██", "█ █ █", "█   █", "█   █"],
    "A": [" ███ ", "█   █", "█████", "█   █", "█   █"],
    "R": ["████ ", "█   █", "████ ", "█  █ ", "█   █"],
    "C": [" ████", "█    ", "█    ", "█    ", " ████"],
    "H": ["█   █", "█   █", "█████", "█   █", "█   █"],
    "Y": ["█   █", " █ █ ", "  █  ", "  █  ", "  █  "],
    "N": ["█   █", "██  █", "█ █ █", "█  ██", "█   █"],
    "G": [" ████", "█    ", "█  ██", "█   █", " ███ "],
    "E": ["█████", "█    ", "████ ", "█    ", "█████"],
    " ": ["   ", "   ", "   ", "   ", "   "],
}
TITULO = "OMARCHY MANAGER"
PALAVRAS = ("OMARCHY", "MANAGER")


def _desenhar(texto: str) -> list[str]:
    return [" ".join(LETRAS[c][i] for c in texto) for i in range(5)]


def banner(largura: int, altura: int) -> list[str]:
    """Uma linha de letras grandes se couber; senão as duas palavras empilhadas; senão texto simples."""
    uma = _desenhar(TITULO)
    if largura >= len(uma[0]) + 2 and altura >= 11:
        return uma
    sup, inf = _desenhar(PALAVRAS[0]), _desenhar(PALAVRAS[1])
    if largura >= len(sup[0]) + 2 and altura >= 16:
        return sup + [""] + inf
    return [TITULO]


class Abertura(ModalScreen[None]):
    DEFAULT_CSS = """
    Abertura { align: center middle; background: $background; }
    Abertura #conteudo { width: auto; height: auto; align-horizontal: center; }
    Abertura #logo { color: $accent; text-style: bold; width: auto; }
    Abertura #sub { color: $text-muted; margin-top: 1; width: 100%; text-align: center; }
    """

    def __init__(self, versao: str = "") -> None:
        super().__init__()
        self.versao = versao

    def compose(self) -> ComposeResult:
        w, h = self.app.size
        with Vertical(id="conteudo"):
            yield Static(Text("\n".join(banner(w, h))), id="logo")
            if h >= 8:
                yield Static(Text(f"Gerenciador do Omarchy {self.versao}\nQualquer tecla ou clique entra"), id="sub")

    def on_mount(self) -> None:
        self.set_timer(1.5, self._sair)

    def _sair(self) -> None:
        if self.is_current:
            self.dismiss(None)

    def on_key(self, ev: events.Key) -> None:
        ev.stop()
        self._sair()

    def on_click(self, ev: events.Click) -> None:
        self._sair()
