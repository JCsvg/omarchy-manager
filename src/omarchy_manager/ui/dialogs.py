"""Diálogos modais: confirmação, aviso e ajuda."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.events import Key
from omarchy_manager.ui.navegacao import NavegacaoMixin
from textual.widgets import Button, DataTable, Input, Label, OptionList, Select, Static

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
#botoes { height: auto; align-horizontal: right; margin-top: 1; }
#botoes Button { margin-left: 1; min-width: 12; }
/* Só o botão em foco tem cor cheia. Antes o botão "primário" ficava colorido mesmo
   sem foco e parecia ser o selecionado. */
#botoes Button, #botoes Button.-primary, #botoes Button.-error {
    background: $panel; color: $foreground; border: tall $panel; text-style: none; background-tint: transparent;
}
#botoes Button.-error { color: $error; }
#botoes Button:focus, #botoes Button.-primary:focus {
    background: $accent; color: $background; border: tall $accent; text-style: bold; background-tint: transparent;
}
#botoes Button.-error:focus { background: $error; color: $background; border: tall $error; text-style: bold; }
#botoes Button:disabled { opacity: 50%; }
.dica-teclas { color: $text-muted; text-style: dim; height: 1; margin-top: 1; }
"""

DICA_BOTOES = "←/→ ou h/l mover · Enter confirmar · Esc cancelar"
DICA_FORMULARIO = "↑/↓ ou Tab mudar de campo · ←/→ entre botões · Enter confirmar · Esc cancelar"
DICA_LISTA = "↑/↓ ou j/k escolher · Enter confirmar · ←/→ botões · Esc cancelar"


class Dialogo(NavegacaoMixin, ModalScreen):
    """Base dos diálogos: setas e hjkl movem o foco, com rodapé dizendo as teclas.

    Esquerda/direita (h/l) andam entre os botões da linha de botões. Cima/baixo (j/k)
    andam entre os controles, ou navegam a lista quando o foco está em uma. Com o foco
    em um campo de texto, as letras e as setas esquerda/direita são do campo.
    """

    DICA = DICA_BOTOES
    FOCO_INICIAL = ""  # seletor CSS; vazio deixa a subclasse decidir

    def on_mount(self) -> None:
        caixas = self.query("#caixa")
        if caixas and not self.query(".dica-teclas"):
            caixas.first().mount(Static(self.DICA, classes="dica-teclas"))
        if self.FOCO_INICIAL:
            alvo = self.query(self.FOCO_INICIAL)
            if alvo:
                alvo.first().focus()

    def _botoes(self) -> list[Button]:
        return [b for b in self.query("#botoes Button") if not b.disabled and b.display]

    def _mover_entre_botoes(self, passo: int) -> None:
        botoes = self._botoes()
        if not botoes:
            return
        foco = self.focused
        if foco in botoes:
            botoes[(botoes.index(foco) + passo) % len(botoes)].focus()
        else:
            (botoes[0] if passo > 0 else botoes[-1]).focus()

    def on_key(self, ev: Key) -> None:
        foco = self.focused
        tecla = ev.key
        if isinstance(foco, Input):
            if tecla in ("up", "down"):
                ev.stop()
                self.focus_previous() if tecla == "up" else self.focus_next()
            return
        if tecla in ("left", "h", "right", "l"):
            ev.stop()
            ev.prevent_default()
            self._mover_entre_botoes(-1 if tecla in ("left", "h") else 1)
        elif tecla in ("j", "k"):
            ev.stop()
            ev.prevent_default()
            if isinstance(foco, (OptionList, DataTable)):
                foco.action_cursor_down() if tecla == "j" else foco.action_cursor_up()
            else:
                self.focus_next() if tecla == "j" else self.focus_previous()
        elif tecla in ("up", "down") and not isinstance(foco, (OptionList, DataTable, Select)):
            ev.stop()
            ev.prevent_default()
            self.focus_next() if tecla == "down" else self.focus_previous()



class Confirmacao(Dialogo):
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

    FOCO_INICIAL = "#cancelar"  # em confirmação, o foco começa sempre no lado seguro

    def on_button_pressed(self, ev: Button.Pressed) -> None:
        self.dismiss(ev.button.id == "ok")

    def action_cancelar(self) -> None:
        self.dismiss(False)


class Aviso(Dialogo):
    DICA = "Enter ou Esc fechar"
    FOCO_INICIAL = "#ok"

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
  1 a 7             ir para uma aba (Atalhos ... Compartilhar)
  8                 aba Webapps (só quando ativada na Config)
  ↑ ↓ ou j k        navegar na lista
  Enter             executar a ação em foco
  /                 pesquisar
  Esc               cancelar ou voltar

[b]Diálogos[/b]
  ← → ou h l        mover entre os botões
  ↑ ↓ ou j k        mover entre campos, ou escolher na lista
  Enter             ativar o botão em foco (o botão em foco é o de cor cheia)
  Esc               cancelar
  ?                 esta ajuda
  q                 sair

[b]Aba Temas[/b]
  h l ou ← →        trocar o fundo exibido; o exibido vira o padrão do tema
  p                 lista de fundos (e tirar o padrão)
  v                 prévia ao vivo (aplica de verdade; v ou Esc desfaz)
  Enter             aplicar o tema com o fundo padrão

[b]Outras teclas[/b]
  Alt+H / Alt+L     aba anterior / próxima (de qualquer lugar)
  4                 aba Config, com todos os atalhos
  5                 aba Fundo, imagem da tela sem trocar de tema
  6                 aba Terminal, opacidade, fonte, cursor e prompt
  7                 aba Compartilhar, oferecer e receber pela rede local

[b]Mouse[/b]
  clique            selecionar ou ativar
  passar o mouse    mostrar descrição

[b]Segurança[/b]
  Nada é gravado em /usr/share/omarchy/.
  Toda alteração de atalho gera backup e é desfeita sozinha se o Hyprland
  reportar erro de configuração.
  Plugins do Omarchy Shell rodam sem sandbox: instale só o que você confia.
"""


class Ajuda(Dialogo):
    DICA = "↑/↓ ou j/k rolar · Enter ou Esc fechar"
    FOCO_INICIAL = "#ok"

    def on_key(self, ev: Key) -> None:
        if ev.key in ("j", "down", "k", "up"):
            ev.stop()
            ev.prevent_default()
            caixa = self.query_one("#caixa")
            caixa.scroll_down() if ev.key in ("j", "down") else caixa.scroll_up()

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
