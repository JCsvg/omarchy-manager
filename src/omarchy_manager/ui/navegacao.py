"""Navegação só por teclado, igual em todas as abas e diálogos.

Esquema único:
- Ctrl+↓ ou Ctrl+j: próxima zona; Ctrl+↑ ou Ctrl+k: zona anterior (sem dar a volta);
- Ctrl+→/← ou Ctrl+l/h: próximo/anterior botão da zona (dá a volta); Ctrl+Enter aperta;
- Ctrl+Espaço (ou F1): painel de ajuda da aba; Esc: volta o foco para a lista.

Uma "zona" é um controle focável. Botões em sequência formam uma só zona, e a fileira de
botões logo abaixo de uma tabela entra na zona da tabela. A aba pode listar as zonas à mão em `SECOES`.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import ScrollableContainer, Vertical
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Button, DataTable, Footer, Input, Label, OptionList, Select, Static
from textual.widgets._footer import FooterKey

COMUM = """[b]Navegação (igual em todas as abas)[/b]
  Ctrl+↓ / Ctrl+j      próximo campo ou seção
  Ctrl+↑ / Ctrl+k      campo ou seção anterior
  ↑ ↓ / j k            linhas da lista
  Ctrl+← → / Ctrl+h l  entre botões
  Ctrl+Enter           aperta o botão
  Esc                  volta para a lista
  Alt+H / Alt+L        aba anterior / próxima
  1 a 7                ir para a aba"""
FINAL = """[b]Geral[/b]
  F5                   recarregar
  ?                    ajuda completa
  q                    sair"""


def eh_controle(w: Widget) -> bool:
    """Focável de verdade: fora painéis de rolagem (focáveis só para rolar) e o miolo do Select."""
    if not w.focusable:
        return False
    if isinstance(w, ScrollableContainer) and not isinstance(w, (DataTable, OptionList)):
        return False
    return not any(isinstance(a, Select) for a in w.ancestors)


def _nome(tecla: str) -> str:
    from omarchy_manager.ui.config import tecla_legivel

    return tecla_legivel(tecla)


def ajuda_da_aba(aba) -> str:
    """Texto do painel: bloco comum, teclas da própria aba (tiradas de BINDINGS) e geral."""
    if getattr(aba, "AJUDA", ""):
        return aba.AJUDA
    linhas = []
    for b in type(aba).BINDINGS:
        if isinstance(b, Binding) and b.description and b.key not in ("j", "k", "slash"):
            teclas = b.key_display or " / ".join(_nome(k.strip()) for k in b.key.split(","))
            linhas.append(f"  {teclas:<20} {b.description}")
    meio = "\n[b]Nesta aba[/b]\n" + "\n".join(linhas) + "\n" if linhas else "\n"
    return COMUM + "\n" + meio + FINAL


class AjudaAba(ModalScreen):
    """Painel de teclas, estilo which-key. Esc, q, Ctrl+Espaço ou F1 fecham."""

    DEFAULT_CSS = """
    AjudaAba { align: center middle; }
    AjudaAba #caixa { width: 62; height: auto; max-height: 95%; background: $surface; border: round $accent; padding: 0 2; }
    AjudaAba .titulo { text-style: bold; color: $accent; }
    AjudaAba .mudo { color: $text-muted; }
    """
    BINDINGS = [Binding("escape,q,ctrl+@,ctrl+space,ctrl+at,f1", "fechar", "Fechar", priority=True)]

    def __init__(self, titulo: str, texto: str) -> None:
        super().__init__()
        self._titulo, self._texto = titulo, texto

    def compose(self) -> ComposeResult:
        with Vertical(id="caixa"):
            yield Label(f"Teclas: {self._titulo}", classes="titulo")
            yield Static(self._texto)
            yield Static("Esc, q ou Ctrl+Espaço fecham", classes="mudo")

    def action_fechar(self) -> None:
        self.dismiss(None)


class NavegacaoMixin:
    """Para abas e diálogos: zonas focáveis, Ctrl+j/k entre elas, fileira de botões, rodapé e ajuda."""

    SECOES: tuple[tuple[str, ...], ...] = ()  # opcional: zonas à mão, por seletor (o primeiro é a entrada)
    RODAPE: tuple[str, ...] = ()  # ações do rodapé, em ordem (as teclas de letra só valem fora de campos)
    TITULO_AJUDA = ""

    def zonas(self) -> list[list[Widget]]:
        if self.SECOES:
            saida = []
            for seletores in self.SECOES:
                z = [w for s in seletores for w in self.query(s) if w.focusable]  # type: ignore[attr-defined]
                if z:
                    saida.append(z)
            return saida
        zonas: list[list[Widget]] = []
        for w in self.query("*"):  # type: ignore[attr-defined]
            if not eh_controle(w):
                continue
            if isinstance(w, Button) and zonas:
                ult = zonas[-1]
                if isinstance(ult[-1], Button) and ult[-1].parent is w.parent:
                    ult.append(w)
                    continue
                if isinstance(ult[0], DataTable) and len(ult) == 1:
                    ult.append(w)
                    continue
            zonas.append([w])
        return zonas

    def _foco(self) -> Widget | None:
        return self.screen.focused if hasattr(self, "screen") else None  # type: ignore[attr-defined]

    def zona_atual(self, zonas: list[list[Widget]] | None = None) -> int:
        zonas = zonas if zonas is not None else self.zonas()
        f = self._foco()
        for n, z in enumerate(zonas):
            if f in z:
                return n
        return -1

    def focar_zona(self, n: int) -> None:
        zonas = self.zonas()
        if zonas:
            zonas[max(0, min(len(zonas) - 1, n))][0].focus()

    def mover_secao(self, passo: int) -> None:
        zonas = self.zonas()
        if not zonas:
            return
        atual = self.zona_atual(zonas)
        self.focar_zona(0 if atual < 0 else atual + passo)

    def focar_entrada(self) -> None:
        """Foco ao entrar na aba: a lista, se houver; senão o primeiro campo."""
        zonas = self.zonas()
        for z in zonas:
            if isinstance(z[0], DataTable):
                z[0].focus()
                return
        if zonas:
            zonas[0][0].focus()

    def fileira(self) -> list[Widget]:
        """Controles que Ctrl+←/→ percorrem a partir do foco atual (vazio: use os botões da aba)."""
        zonas = self.zonas()
        n = self.zona_atual(zonas)
        if n < 0:
            return []
        z = zonas[n]
        if isinstance(z[0], Button):
            return []  # só botões: Ctrl+←/→ percorrem todos os botões da aba
        resto = z[1:] if isinstance(z[0], (DataTable, OptionList)) else z
        return resto if len(resto) > 1 or (resto and resto[0] is not self._foco()) else []

    def acoes_do_rodape(self) -> list[str]:
        f = self._foco()
        nav = ["secao", "ajuda_aba"]
        if isinstance(f, Button):
            return ["botao_acionar", "botao"] + nav
        if isinstance(f, (Input, Select)):
            return nav
        return list(self.RODAPE)[:3] + nav

    def texto_ajuda(self) -> str:
        return ajuda_da_aba(self)


class RodapeEnxuto(Footer):
    """Mostra só as teclas da zona focada (no máximo 5). Em diálogo, o rodapé padrão."""

    def compose(self) -> ComposeResult:
        aba = None
        try:
            if len(self.app.screen_stack) == 1:
                aba = self.app.nav_da_aba()
        except Exception:
            aba = None
        if aba is None:
            yield from super().compose()
            return
        if not self._bindings_ready:
            return
        permitidas = aba.acoes_do_rodape()
        vistos: dict[str, tuple] = {}
        for _, b, enabled, tooltip in self.screen.active_bindings.values():
            nome = b.action.split("(")[0]
            if nome in permitidas and nome not in vistos and (b.show or nome == "buscar"):
                vistos[nome] = (b, enabled, tooltip)
        ordem = [vistos[n] for n in permitidas if n in vistos]
        self.styles.grid_size_columns = len(ordem)
        for b, enabled, tooltip in ordem:
            yield FooterKey(b.key, self.app.get_key_display(b), b.description, b.action,
                            disabled=not enabled, tooltip=tooltip).data_bind(compact=Footer.compact)
