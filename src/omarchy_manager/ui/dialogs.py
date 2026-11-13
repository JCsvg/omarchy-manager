"""Diálogos modais: confirmação, aviso e ajuda."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static

CSS_DIALOGO = """
Confirmacao, Aviso, Ajuda {
    align: center middle;
}
#caixa {
    width: 70;
    max-width: 95%;
    height: auto;
    max-height: 90%;
    border: thick $accent;
    background: $surface;
    padding: 1 2;
}
#caixa Label { margin-bottom: 1; }
#caixa .titulo { text-style: bold; color: $accent; }
#caixa .perigo { color: $error; }
#botoes { height: auto; align-horizontal: right; }
#botoes Button { margin-left: 1; min-width: 12; }
"""


class Confirmacao(ModalScreen[bool]):
    """Pergunta sim ou não. Esc e `Cancelar` devolvem False."""

    DEFAULT_CSS = CSS_DIALOGO
    BINDINGS = [Binding("escape", "cancelar", "Cancelar")]

    def __init__(self, titulo: str, mensagem: str, *, confirmar: str = "Confirmar", perigo: bool = False) -> None:
        super().__init__()
        self._titulo = titulo
        self._mensagem = mensagem
        self._confirmar = confirmar
        self._perigo = perigo

    def compose(self) -> ComposeResult:
        with Vertical(id="caixa"):
            yield Label(self._titulo, classes="titulo" + (" perigo" if self._perigo else ""))
            yield Static(self._mensagem)
            with Horizontal(id="botoes"):
                yield Button("Cancelar", id="cancelar")
                yield Button(self._confirmar, id="ok", variant="error" if self._perigo else "primary")

    def on_mount(self) -> None:
        self.query_one("#cancelar", Button).focus()

    def on_button_pressed(self, ev: Button.Pressed) -> None:
        self.dismiss(ev.button.id == "ok")

    def action_cancelar(self) -> None:
        self.dismiss(False)


class Aviso(ModalScreen[None]):
    DEFAULT_CSS = CSS_DIALOGO
    BINDINGS = [Binding("escape", "fechar", "Fechar"), Binding("enter", "fechar", "Fechar", show=False)]

    def __init__(self, titulo: str, mensagem: str) -> None:
        super().__init__()
        self._titulo = titulo
        self._mensagem = mensagem

    def compose(self) -> ComposeResult:
        with Vertical(id="caixa"):
            yield Label(self._titulo, classes="titulo")
            yield Static(self._mensagem)
            with Horizontal(id="botoes"):
                yield Button("Fechar", id="ok", variant="primary")

    def on_button_pressed(self, _: Button.Pressed) -> None:
        self.dismiss(None)

    def action_fechar(self) -> None:
        self.dismiss(None)


TEXTO_AJUDA = """\
[b]Navegação[/b]
  Tab / Shift+Tab   mudar o foco
  1, 2, 3           ir para Atalhos, Plugins, Temas
  ↑ ↓ ou j k        navegar na lista
  Enter             executar a ação em foco
  /                 pesquisar
  Esc               cancelar ou voltar
  ?                 esta ajuda
  q                 sair

[b]Mouse[/b]
  clique            selecionar ou ativar
  passar o mouse    mostrar descrição

[b]Segurança[/b]
  Nada é gravado em /usr/share/omarchy/.
  Toda alteração de atalho gera backup e é desfeita sozinha se o Hyprland
  reportar erro de configuração.
  Plugins do Omarchy Shell rodam sem sandbox: instale só o que você confia.
"""


class Ajuda(ModalScreen[None]):
    DEFAULT_CSS = CSS_DIALOGO
    BINDINGS = [Binding("escape", "fechar", "Fechar"), Binding("question_mark", "fechar", "Fechar", show=False)]

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="caixa"):
            yield Label("Ajuda", classes="titulo")
            yield Static(TEXTO_AJUDA)
            with Horizontal(id="botoes"):
                yield Button("Fechar", id="ok", variant="primary")

    def on_button_pressed(self, _: Button.Pressed) -> None:
        self.dismiss(None)

    def action_fechar(self) -> None:
        self.dismiss(None)
