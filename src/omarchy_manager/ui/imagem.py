"""Widget que mostra uma imagem em pixels de verdade (Sixel ou protocolo kitty).

A técnica é a mesma da biblioteca textual-image: o widget entrega linhas em
branco ao Textual e pendura na última linha um segmento de controle que move
o cursor para o canto do widget e escreve a imagem. Assim é o compositor do
Textual que decide quando redesenhar, e a imagem some quando a região é
repintada por outra coisa (troca de aba, diálogo).

A imagem só é emitida quando o widget está inteiro na tela e a tela está
ativa. A codificação roda em thread, com cache por (arquivo, tamanho).
"""

from __future__ import annotations

from pathlib import Path

from rich.control import Control
from rich.segment import ControlType, Segment
from rich.style import Style
from textual import work
from textual.dom import NoScreen
from textual.geometry import Region
from textual.strip import Strip
from textual.widget import Widget

from omarchy_manager.services import imagem as gerador
from omarchy_manager.services import terminal_grafico

_NULO = Style()
ID_KITTY = 4217


class ImagemTerminal(Widget, can_focus=False):
    DEFAULT_CSS = "ImagemTerminal { width: 1fr; height: 1fr; }"

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self._imagem: Path | None = None
        self._chave: tuple | None = None
        self._pronto: tuple[str, int, int, str] | None = None  # sequência, colunas, linhas, protocolo
        self._cache: dict[tuple, tuple[str, int, int, str] | None] = {}
        self._timer = None
        self._kitty_na_tela = False
        self.falhou = False

    def mostrar(self, imagem: Path | None) -> None:
        if imagem == self._imagem and self._pronto is not None:
            return
        self._imagem = imagem
        self._agendar()

    def on_resize(self) -> None:
        self._agendar()

    def _agendar(self) -> None:
        if self._timer is not None:
            self._timer.stop()
        self._timer = self.set_timer(0.12, self._atualizar)

    def _atualizar(self) -> None:
        self._timer = None
        proto = terminal_grafico.protocolo()
        cel_l, cel_a = terminal_grafico.tamanho_celula()
        if self._imagem is None or proto is None or self.size.width < 4 or self.size.height < 2:
            self._chave, self._pronto = None, None
            self.refresh()
            return
        chave = (str(self._imagem), self.size.width, self.size.height, cel_l, cel_a, proto)
        self._chave = chave
        if chave in self._cache:
            self._pronto = self._cache[chave]
            self.falhou = self._pronto is None
            self.refresh()
            return
        self._pronto = None
        self.refresh()
        self._gerar(chave)

    @work(thread=True, group="imagem-terminal")
    def _gerar(self, chave: tuple) -> None:
        caminho, colunas, linhas, cel_l, cel_a, proto = chave
        resultado = None
        origem = gerador.intermediario(Path(caminho))
        if origem is not None and chave == self._chave:  # o usuário pode já ter ido para outro tema
            if proto == "kitty":
                bruto = gerador.kitty(origem, colunas * cel_l, linhas * cel_a, ID_KITTY)
            else:
                bruto = gerador.sixel(origem, colunas * cel_l, linhas * cel_a)
            if bruto is not None:
                dados, larg_px, alt_px = bruto
                resultado = (dados, -(-larg_px // cel_l), -(-alt_px // cel_a), proto)
        elif origem is not None:
            return
        self.app.call_from_thread(self._gerado, chave, resultado)

    def _gerado(self, chave: tuple, resultado) -> None:
        if len(self._cache) > 24:
            self._cache.clear()
        self._cache[chave] = resultado
        if chave == self._chave:
            self._pronto = resultado
            self.falhou = resultado is None
            self.refresh()

    def apagar(self) -> None:
        """Remove a imagem kitty da tela (o Sixel some sozinho quando a região é repintada)."""
        if not self._kitty_na_tela:
            return
        self._kitty_na_tela = False
        try:
            driver = self.app._driver
            if driver is not None:
                driver.write(gerador.kitty_apagar(ID_KITTY))
                driver.flush()
        except Exception:
            pass

    def on_hide(self) -> None:
        self.apagar()

    def on_unmount(self) -> None:
        self.apagar()

    def render_lines(self, crop: Region) -> list[Strip]:
        _, cor = self.background_colors
        fundo = Style(bgcolor=cor.rich_color)
        branco = Segment(" " * crop.width, fundo)
        linhas = [Strip([branco], crop.width) for _ in range(crop.height)]
        if not linhas:
            return linhas
        try:
            ativa = self.screen.is_active
            visivel = self.screen.find_widget(self).visible_region
        except (NoScreen, Exception):
            return linhas
        inteiro = (
            crop.x == 0 and crop.y == 0 and crop.width == self.size.width and crop.height == self.size.height
            and visivel.width == self.size.width and visivel.height == self.size.height
        )
        atual = self._chave is not None and self._chave[1:3] == (self.size.width, self.size.height)  # gerada para este tamanho
        if self._pronto is None or not ativa or not inteiro or not atual:
            if self._kitty_na_tela:  # diálogo por cima ou widget cortado: tira a imagem kitty
                self._kitty_na_tela = False
                linhas[-1] = Strip([branco, Segment(gerador.kitty_apagar(ID_KITTY), _NULO, control=((ControlType.CURSOR_FORWARD, 0),))], crop.width)
            elif self._pronto is None and self._imagem is not None and not self.falhou and crop.width >= 22:
                texto = "carregando a imagem…"
                linhas[0] = Strip([Segment(texto, fundo + Style(dim=True)), Segment(" " * (crop.width - len(texto)), fundo)], crop.width)
            return linhas
        dados, colunas, _, proto = self._pronto
        x = visivel.x + max(0, (self.size.width - colunas) // 2)
        self._kitty_na_tela = proto == "kitty"
        linhas[-1] = Strip(
            [
                branco,
                Segment(Control.move_to(x, visivel.y).segment.text, _NULO),
                Segment(dados, _NULO, control=((ControlType.CURSOR_FORWARD, 0),)),
                Segment(Control.move_to(visivel.right, visivel.bottom - 1).segment.text, _NULO),
            ],
            crop.width,
        )
        return linhas
