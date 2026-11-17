"""Aba Fundo: escolhe qualquer imagem como fundo da tela, sem trocar de tema."""

from __future__ import annotations

from pathlib import Path

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Input, Static

from omarchy_manager.services import fundo_livre
from omarchy_manager.ui.imagem import ImagemTerminal


class AbaFundo(Vertical):
    DEFAULT_CSS = """
    AbaFundo { height: 1fr; }
    #fundo-corpo { height: 1fr; }
    #fundo-esq { width: 1fr; }
    #fundo-dir { width: 1fr; padding-left: 1; }
    #fundo-titulo { color: $accent; text-style: bold; height: 1; }
    #fundo-atual { color: $text-muted; height: 2; }
    #fundo-tabela { height: 1fr; }
    #fundo-previa { height: 1fr; }
    #fundo-info { height: 2; color: $text-muted; }
    #fundo-botoes { height: auto; }
    #fundo-status { height: 1; }
    """
    BINDINGS = [
        Binding("j", "cursor_baixo", "Descer", show=False),
        Binding("k", "cursor_cima", "Subir", show=False),
        Binding("enter", "aplicar", "Usar como fundo"),
        Binding("u", "voltar", "Voltar ao fundo anterior"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._imagens: list[Path] = []
        self._anterior: Path | None = None
        self._pasta: Path | None = None

    def compose(self) -> ComposeResult:
        yield Static("Fundo da tela (sem trocar de tema)", id="fundo-titulo")
        yield Static("", id="fundo-atual")
        with Horizontal(id="fundo-corpo"):
            with Vertical(id="fundo-esq"):
                tabela = DataTable(id="fundo-tabela", cursor_type="row", zebra_stripes=True)
                tabela.add_columns("Imagem", "Subpasta")
                yield tabela
                yield Input(placeholder="Pasta das imagens (ou uma imagem), Enter confirma", id="fundo-caminho")
            with Vertical(id="fundo-dir"):
                yield ImagemTerminal(id="fundo-previa")
                yield Static("", id="fundo-info")
        with Horizontal(id="fundo-botoes"):
            yield Button("Usar como fundo", id="fundo-aplicar", variant="primary")
            yield Button("Voltar ao anterior", id="fundo-voltar")
        yield Static("", id="fundo-status")

    def on_mount(self) -> None:
        self.recarregar()

    def on_show(self) -> None:
        self.call_after_refresh(self._mostrar_atual)

    def recarregar(self) -> None:
        self._pasta = fundo_livre.pasta_escolhida()
        self._imagens = fundo_livre.listar(self._pasta)
        tabela = self.query_one("#fundo-tabela", DataTable)
        tabela.clear()
        for img in self._imagens:
            tabela.add_row(img.name, self._subpasta(img), key=str(img))
        atual = self.app.omarchy.theme_bg_current_path()
        self.query_one("#fundo-atual", Static).update(
            f"Fundo atual: {atual}" if atual else "Fundo atual: não foi possível ler"
        )
        if not self._imagens:
            self._status(
                "Digite abaixo o caminho da pasta com as suas imagens e aperte Enter."
                if self._pasta is None
                else f"Nenhuma imagem png, jpg ou webp em {self._pasta}."
            )
        else:
            self._status(f"Pasta: {self._pasta}  ({len(self._imagens)} imagens)")
        campo = self.query_one("#fundo-caminho", Input)
        if self._pasta is not None and not campo.value:
            campo.value = str(self._pasta)

    def _subpasta(self, img: Path) -> str:
        if self._pasta is None:
            return ""
        try:
            rel = img.parent.relative_to(self._pasta.resolve())
        except ValueError:
            return str(img.parent)
        return str(rel) if str(rel) != "." else ""

    def action_buscar(self) -> None:
        pass

    def _status(self, texto: str) -> None:
        self.query_one("#fundo-status", Static).update(texto)

    def _selecionada(self) -> Path | None:
        tabela = self.query_one("#fundo-tabela", DataTable)
        if not self._imagens or tabela.row_count == 0:
            return None
        linha = tabela.cursor_row
        return self._imagens[linha] if 0 <= linha < len(self._imagens) else None

    def _mostrar_atual(self) -> None:
        img = self._selecionada()
        self.query_one("#fundo-previa", ImagemTerminal).mostrar(img)
        info = self.query_one("#fundo-info", Static)
        if img is None:
            info.update("")
            return
        try:
            kb = img.stat().st_size // 1024
        except OSError:
            kb = 0
        info.update(f"{img.name}  ({kb} KB)\nEnter aplica, u volta ao anterior. Vale até a próxima troca de tema.")

    @on(DataTable.RowHighlighted, "#fundo-tabela")
    def _linha_mudou(self) -> None:
        self._mostrar_atual()

    @on(DataTable.RowSelected, "#fundo-tabela")
    def _linha_escolhida(self) -> None:
        self.action_aplicar()

    @on(Button.Pressed, "#fundo-aplicar")
    def action_aplicar(self) -> None:
        img = self._selecionada()
        if img is None:
            self._status("Escolha uma imagem na lista.")
            return
        self._aplicar(img)

    @on(Button.Pressed, "#fundo-voltar")
    def action_voltar(self) -> None:
        if self._anterior is None:
            self._status("Ainda não há fundo anterior nesta sessão.")
            return
        self._aplicar(self._anterior, registrar=False)

    @work(thread=True, exclusive=True, group="fundo-aplicar")
    def _aplicar(self, img: Path, registrar: bool = True) -> None:
        antes = self.app.omarchy.theme_bg_current_path()
        resultado = self.app.omarchy.theme_bg_set(img)
        self.app.call_from_thread(self._aplicado, img, antes if registrar else None, resultado)

    def _aplicado(self, img: Path, antes: Path | None, resultado) -> None:
        if not resultado.ok:
            self._status(f"Falhou: {resultado.erro_legivel}")
            self.app.notify(f"Não foi possível aplicar o fundo: {resultado.erro_legivel}", severity="error")
            return
        if antes is not None and antes != img:
            self._anterior = antes
        self.query_one("#fundo-atual", Static).update(f"Fundo atual: {img}")
        self._status(f"Fundo aplicado: {img.name}")

    @on(Input.Submitted, "#fundo-caminho")
    def _caminho_digitado(self, evento: Input.Submitted) -> None:
        bruto = evento.value.strip()
        if not bruto:
            return
        caminho = Path(bruto).expanduser()
        if caminho.is_dir():
            fundo_livre.definir_pasta(caminho)
            evento.input.value = str(caminho.resolve())
            self.recarregar()
        elif fundo_livre.eh_imagem(caminho):
            self._aplicar(caminho)
        else:
            self._status("Não é uma pasta nem uma imagem png, jpg ou webp.")

    def action_cursor_baixo(self) -> None:
        self.query_one("#fundo-tabela", DataTable).action_cursor_down()

    def action_cursor_cima(self) -> None:
        self.query_one("#fundo-tabela", DataTable).action_cursor_up()
