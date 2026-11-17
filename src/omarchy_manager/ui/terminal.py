"""Aba Terminal: opacidade, fonte, margem, cursor e o prompt do terminal padrão."""

from __future__ import annotations

from textual import events, on
from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Button, Input, Label, Select, Static, Switch

from omarchy_manager.services import arquivos, prompt_posh, terminal_cfg


class CampoNumerico(Input):
    """Campo de número em que ↑ → k aumentam e ↓ ← j diminuem, dentro de um intervalo."""

    def __init__(self, *, passo: float, minimo: float, maximo: float, decimal: bool = False, **kw) -> None:
        super().__init__(type="number" if decimal else "integer", **kw)
        self.passo, self.minimo, self.maximo, self.decimal = passo, minimo, maximo, decimal

    def ajustar(self, sentido: int) -> None:
        try:
            atual = float(self.value)
        except ValueError:
            atual = self.minimo
        novo = round(min(self.maximo, max(self.minimo, atual + sentido * self.passo)), 2)
        self.value = f"{novo:g}" if self.decimal else str(int(novo))
        self.cursor_position = len(self.value)

    def on_key(self, evento: events.Key) -> None:
        if evento.key in ("up", "right", "k"):
            self.ajustar(1)
        elif evento.key in ("down", "left", "j"):
            self.ajustar(-1)
        else:
            return
        evento.prevent_default()
        evento.stop()


class AbaTerminal(VerticalScroll):
    DEFAULT_CSS = """
    AbaTerminal { height: 1fr; }
    AbaTerminal .secao { color: $accent; text-style: bold; height: 1; margin-top: 1; }
    AbaTerminal .linha { height: 3; }
    AbaTerminal .linha Label { width: 26; padding-top: 1; }
    AbaTerminal .linha Input { width: 24; }
    AbaTerminal .linha Select { width: 24; }
    AbaTerminal .dica { color: $text-muted; height: auto; }
    AbaTerminal .botoes { height: auto; }
    #term-status { height: auto; margin-top: 1; }
    """

    def compose(self) -> ComposeResult:
        yield Static("Terminal padrão: …", id="term-titulo", classes="secao")
        yield Static("", id="term-aviso", classes="dica")
        yield Static("Nos campos de número, ↑/↓ ou j/k mudam o valor. Tab troca de campo.", classes="dica")
        with Horizontal(classes="linha"):
            yield Label("Opacidade (10 a 100 %)")
            yield CampoNumerico(id="term-opacidade", passo=5, minimo=10, maximo=100)
        with Horizontal(classes="linha"):
            yield Label("Fonte")
            yield Input(id="term-fonte")
        with Horizontal(classes="linha"):
            yield Label("Tamanho da fonte")
            yield CampoNumerico(id="term-tamanho", passo=0.5, minimo=4, maximo=48, decimal=True)
        with Horizontal(classes="linha"):
            yield Label("Margem interna (px)")
            yield CampoNumerico(id="term-margem", passo=1, minimo=0, maximo=100)
        with Horizontal(classes="linha"):
            yield Label("Cursor")
            yield Select([(c, c) for c in terminal_cfg.CURSORES], id="term-cursor", allow_blank=False)
        with Horizontal(classes="linha"):
            yield Label("Cursor piscando")
            yield Switch(id="term-piscar")
        with Horizontal(classes="linha"):
            yield Label("Histórico (linhas)")
            yield CampoNumerico(id="term-historico", passo=1000, minimo=0, maximo=1000000)
        with Horizontal(classes="botoes"):
            yield Button("Aplicar", id="term-aplicar", variant="primary")
            yield Button("Desfazer última mudança", id="term-desfazer")
        yield Static("A opacidade vale na hora neste terminal. O resto vale para janelas novas.", classes="dica")
        yield Static("Prompt", classes="secao")
        yield Static(
            "Powerline (Oh My Posh, tema no estilo M365Princess): usuário, diretório, git, .NET e hora "
            "em segmentos unidos por setas. Só acrescenta um bloco ao ~/.bashrc, com backup. "
            "Precisa de Nerd Font (já vem no Omarchy).",
            id="term-prompt-info",
            classes="dica",
        )
        with Horizontal(classes="botoes"):
            yield Button("Ligar prompt powerline", id="term-prompt-aplicar", variant="primary")
            yield Button("Desligar prompt powerline", id="term-prompt-restaurar")
        yield Static("", id="term-status")

    def on_mount(self) -> None:
        self.recarregar()

    def action_buscar(self) -> None:
        pass

    def recarregar(self) -> None:
        nome = terminal_cfg.terminal_padrao() or "desconhecido"
        self.query_one("#term-titulo", Static).update(f"Terminal padrão: {nome}  ({terminal_cfg.arquivo_foot()})")
        suportado = nome in ("foot", "desconhecido") and terminal_cfg.foot_instalado()
        self.query_one("#term-aviso", Static).update(
            "" if suportado else f"Por enquanto só o Foot é suportado; as mudanças abaixo vão para o foot.ini e não afetam o {nome}."
        )
        cfg = terminal_cfg.ler()
        self.query_one("#term-opacidade", Input).value = str(cfg.opacidade)
        self.query_one("#term-fonte", Input).value = cfg.fonte
        self.query_one("#term-tamanho", Input).value = terminal_cfg._fmt_tamanho(cfg.tamanho)
        self.query_one("#term-margem", Input).value = str(cfg.margem)
        self.query_one("#term-cursor", Select).value = cfg.cursor
        self.query_one("#term-piscar", Switch).value = cfg.piscar
        self.query_one("#term-historico", Input).value = str(cfg.historico)

    def _status(self, texto: str, classe: str = "ok") -> None:
        s = self.query_one("#term-status", Static)
        s.set_classes(classe)
        s.update(texto)

    def _ler_formulario(self) -> terminal_cfg.ConfigTerminal | None:
        atual = terminal_cfg.ler()
        try:
            return terminal_cfg.validar(
                terminal_cfg.ConfigTerminal(
                    opacidade=int(self.query_one("#term-opacidade", Input).value or atual.opacidade),
                    fonte=self.query_one("#term-fonte", Input).value,
                    tamanho=float(self.query_one("#term-tamanho", Input).value or atual.tamanho),
                    margem=int(self.query_one("#term-margem", Input).value or atual.margem),
                    cursor=str(self.query_one("#term-cursor", Select).value),
                    piscar=self.query_one("#term-piscar", Switch).value,
                    historico=int(self.query_one("#term-historico", Input).value or atual.historico),
                )
            )
        except ValueError:
            self._status("Há um número inválido no formulário.", "erro")
            return None

    @on(Button.Pressed, "#term-aplicar")
    def _aplicar(self) -> None:
        cfg = self._ler_formulario()
        if cfg is None:
            return
        try:
            backup = terminal_cfg.gravar(cfg)
        except OSError as exc:
            self._status(f"Não foi possível gravar o foot.ini: {exc}", "erro")
            return
        self.app.reafirmar_transparencia()
        self.recarregar()
        self._status(f"Salvo em foot.ini ({'backup feito' if backup else 'arquivo novo'}).")

    @on(Button.Pressed, "#term-desfazer")
    def _desfazer(self) -> None:
        backup = arquivos.restaurar_ultimo(terminal_cfg.arquivo_foot())
        if backup is None:
            self._status("Não há backup do foot.ini.", "aviso")
            return
        self.app.reafirmar_transparencia()
        self.recarregar()
        self._status(f"foot.ini restaurado de {backup.name}.")

    @on(Button.Pressed, "#term-prompt-aplicar")
    def _prompt_aplicar(self) -> None:
        ok, msg = prompt_posh.ativar()
        self._status(msg, "ok" if ok else "erro")

    @on(Button.Pressed, "#term-prompt-restaurar")
    def _prompt_restaurar(self) -> None:
        ok, msg = prompt_posh.desativar()
        self._status(msg, "ok" if ok else "aviso")
