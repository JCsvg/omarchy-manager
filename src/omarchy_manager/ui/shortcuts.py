"""Aba Atalhos: tabela dos bindings efetivos, pesquisa, filtros por origem e
plugin, detalhe lateral, edição com captura, conflito antes de gravar,
gravação segura com rollback e desfazer."""

from __future__ import annotations

from pathlib import Path

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.coordinate import Coordinate
from textual.events import Key
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Input, Label, Select, Static

from omarchy_manager.models import Atalho
from omarchy_manager.services.lua_scan import atalhos_completos
from omarchy_manager.services.overrides import ErroAplicacao, ErroOverrides, Override
from omarchy_manager.services.plugin_catalog import atalhos_do_plugin, ler_aliases
from omarchy_manager.services.shortcut_capture import combinacao_de_tecla_textual
from omarchy_manager.services.teclas import Combinacao
from omarchy_manager.ui.dialogs import CSS_DIALOGO, Aviso, Confirmacao
from omarchy_manager.ui.navegacao import NavegacaoMixin

ORIGENS = [("Todas as origens", "todas"), ("Omarchy", "omarchy"), ("Usuário", "usuario"), ("Plugin", "plugin"), ("Gerenciador", "gerenciador")]
ROTULO_ORIGEM = {"omarchy": "Omarchy", "usuario": "usuário", "plugin": "plugin", "gerenciador": "gerenciador", "desconhecida": "?"}


class CapturaTecla(ModalScreen[Combinacao | None]):
    """Pede a nova combinação. Tenta o submap do Hyprland (captura Super) e,
    em paralelo, aceita a tecla que chegar ao terminal."""

    DEFAULT_CSS = CSS_DIALOGO + """
    CapturaTecla #caixa { width: 64; }
    CapturaTecla #capturada { text-style: bold; color: $accent; height: 3; content-align: center middle; border: round $panel; }
    """
    BINDINGS = [Binding("escape", "cancelar", "Cancelar", priority=True)]

    def __init__(self, atalho: Atalho) -> None:
        super().__init__()
        self.atalho = atalho
        self._resultado: Combinacao | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="caixa"):
            yield Label(f"Nova combinação para: {self.atalho.description or self.atalho.comando}", classes="titulo")
            yield Static(f"Atual: {self.atalho.combinacao}\n\nPressione a nova combinação. Esc cancela.", id="instrucao")
            yield Static("…", id="capturada")
            yield Static("", id="captura-status", classes="mudo")
            yield Static("Qualquer combinação vira o novo atalho · Esc cancelar", classes="dica-teclas")
            with Horizontal(id="botoes"):
                yield Button("Cancelar", id="cancelar")

    def on_mount(self) -> None:
        self.set_focus(None)
        self._capturar_no_hyprland()

    @work(thread=True, exclusive=True, group="captura")
    def _capturar_no_hyprland(self) -> None:
        captura = self.app.captura
        if not captura.iniciar():
            self.app.call_from_thread(self._status, "Captura pelo Hyprland indisponível; usando só o terminal.")
            return
        self.app.call_from_thread(self._status, "Hyprland em modo de captura (15 s).")
        combinacao = captura.esperar()
        if combinacao is not None:
            self.app.call_from_thread(self._concluir, combinacao)
        else:
            self.app.call_from_thread(self._status, "Tempo esgotado no Hyprland; o terminal continua ouvindo.")

    def _status(self, texto: str) -> None:
        if self.is_attached:
            self.query_one("#captura-status", Static).update(texto)

    def on_key(self, ev: Key) -> None:
        if ev.key == "escape":
            return
        ev.stop()
        ev.prevent_default()
        combinacao = combinacao_de_tecla_textual(ev.key)
        if combinacao is None:
            self._status(f"Tecla não reconhecida: {ev.key}")
            return
        self._concluir(combinacao)

    def _concluir(self, combinacao: Combinacao) -> None:
        if self._resultado is not None or not self.is_attached:
            return
        self._resultado = combinacao
        self.query_one("#capturada", Static).update(combinacao.canonica)
        self.app.captura.cancelar()
        self.dismiss(combinacao)

    def on_button_pressed(self) -> None:
        self.action_cancelar()

    def action_cancelar(self) -> None:
        self.app.captura.cancelar()
        self.dismiss(None)


class AbaAtalhos(NavegacaoMixin, Vertical):
    DEFAULT_CSS = """
    AbaAtalhos { height: 1fr; }
    #atalhos-topo { height: 3; }
    #atalhos-busca { width: 1fr; }
    #atalhos-origem { width: 24; }
    #atalhos-plugin { height: 1; color: $warning; }
    #atalhos-corpo { height: 1fr; }
    #atalhos-tabela { width: 2fr; }
    #atalhos-detalhe { width: 1fr; min-width: 32; padding: 0 1; border-left: solid $panel; }
    #atalhos-acoes { height: 3; }
    #atalhos-acoes Button { margin-right: 1; min-width: 10; }
    #atalhos-status { height: 1; color: $text-muted; }
    """
    TITULO_AJUDA = "Atalhos"
    RODAPE = ('editar', 'desfazer', 'buscar')
    BINDINGS = [
        Binding("slash", "buscar", "Pesquisar", key_display="/"),
        Binding("j", "cursor_baixo", "Descer na lista", show=False),
        Binding("k", "cursor_cima", "Subir na lista", show=False),
        Binding("e", "editar", "Editar atalho"),
        Binding("u", "desfazer", "Desfazer"),
        Binding("escape", "limpar", "Limpar pesquisa e filtro de plugin", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.atalhos: list[Atalho] = []
        self._por_linha: dict[int, Atalho] = {}
        self._filtro = ""
        self._origem = "todas"
        self.filtro_plugin = ""

    def compose(self) -> ComposeResult:
        with Horizontal(id="atalhos-topo"):
            yield Input(placeholder="Pesquisar por tecla, ação, comando ou plugin  (/)", id="atalhos-busca")
            yield Select(ORIGENS, value="todas", allow_blank=False, id="atalhos-origem")
        yield Label("", id="atalhos-plugin")
        with Horizontal(id="atalhos-corpo"):
            tabela = DataTable(id="atalhos-tabela", cursor_type="row", zebra_stripes=True)
            tabela.add_columns("Atalho", "Ação", "Origem", "Plugin", "Estado")
            yield tabela
            with VerticalScroll(id="atalhos-detalhe"):
                yield Static("Selecione um atalho.", id="atalhos-detalhe-texto")
        with Horizontal(id="atalhos-acoes"):
            yield Button("Editar", id="btn-editar", variant="primary")
            yield Button("Desfazer última alteração", id="btn-desfazer")
            yield Button("Atualizar", id="btn-atualizar-atalhos")
        yield Label("", id="atalhos-status")

    def on_mount(self) -> None:
        self.recarregar()

    # Carga

    def recarregar(self) -> None:
        self._status("Lendo atalhos do Hyprland…")
        self._carregar()

    @work(thread=True, exclusive=True, group="atalhos-carga")
    def _carregar(self) -> None:
        try:
            pastas = {}
            try:
                brutos = self.app.omarchy.plugin_list_json()
                pastas = {p["id"]: self.app.catalogo.pasta_de(p["id"]) for p in brutos if isinstance(p, dict) and p.get("id")}
                pastas = {k: v for k, v in pastas.items() if v is not None}
            except Exception:
                pass
            atalhos = atalhos_completos(self.app.hyprland, pastas)
        except Exception as exc:
            self.app.call_from_thread(self._status, f"Falha ao ler atalhos: {exc}", "erro")
            return
        self.app.call_from_thread(self._preencher, atalhos)

    def _preencher(self, atalhos: list[Atalho]) -> None:
        self.atalhos = atalhos
        self._renderizar()
        dups = sum(1 for a in atalhos if a.duplicado)
        sem = sum(1 for a in atalhos if not a.comando)
        self._status(f"{len(atalhos)} atalhos, {dups} duplicados, {sem} sem comando conhecido")

    def _visiveis(self) -> list[Atalho]:
        lista = self.atalhos
        if self.filtro_plugin:
            lista = atalhos_do_plugin(self.filtro_plugin, lista, ler_aliases())
        if self._origem != "todas":
            lista = [a for a in lista if a.origem == self._origem]
        termo = self._filtro.lower()
        if termo:
            lista = [a for a in lista if termo in f"{a.combinacao} {a.description} {a.comando} {a.plugin_id}".lower()]
        return lista

    def _renderizar(self) -> None:
        tabela = self.query_one("#atalhos-tabela", DataTable)
        tabela.clear()
        self._por_linha.clear()
        for i, a in enumerate(self._visiveis()):
            estado = []
            if a.duplicado:
                estado.append("duplicado")
            if a.submap:
                estado.append(f"submap {a.submap}")
            if not a.comando:
                estado.append("sem comando")
            if a.origem == "gerenciador":
                estado.append("gerenciado")
            tabela.add_row(
                a.combinacao,
                a.description or "(sem descrição)",
                ROTULO_ORIGEM.get(a.origem, "?"),
                a.plugin_id or "",
                ", ".join(estado) or "ok",
                key=str(i),
            )
            self._por_linha[i] = a
        rotulo = self.query_one("#atalhos-plugin", Label)
        rotulo.update(f"Filtro: atalhos do plugin {self.filtro_plugin}  (Esc limpa)" if self.filtro_plugin else "")
        self._atualizar_detalhe()

    def filtrar_por_plugin(self, plugin_id: str) -> None:
        self.filtro_plugin = plugin_id
        if self.atalhos:
            self._renderizar()
            if not self._visiveis():
                self.app.notify("Nenhum atalho associado foi encontrado para este plugin.", severity="warning")

    # Seleção

    def atalho_selecionado(self) -> Atalho | None:
        tabela = self.query_one("#atalhos-tabela", DataTable)
        if tabela.row_count == 0 or tabela.cursor_row is None:
            return None
        try:
            chave = tabela.coordinate_to_cell_key(Coordinate(tabela.cursor_row, 0)).row_key.value
        except Exception:
            return None
        return self._por_linha.get(int(chave))

    @on(DataTable.RowHighlighted, "#atalhos-tabela")
    def _linha_mudou(self) -> None:
        self._atualizar_detalhe()

    @on(DataTable.RowSelected, "#atalhos-tabela")
    def _linha_ativada(self) -> None:
        self.action_editar()

    def _atualizar_detalhe(self) -> None:
        a = self.atalho_selecionado()
        texto = self.query_one("#atalhos-detalhe-texto", Static)
        editar = self.query_one("#btn-editar", Button)
        if a is None:
            texto.update("Nenhum atalho selecionado.")
            editar.disabled = True
            return
        linhas = [
            f"[b]{a.combinacao}[/b]",
            a.description or "(sem descrição)",
            "",
            f"comando: {a.comando or '(não descoberto)'}",
            f"dispatcher: {a.dispatcher or '?'}" + (f"  arg: {a.arg}" if a.arg and a.dispatcher != "__lua" else ""),
            f"submap: {a.submap or '(raiz)'}",
            f"origem: {ROTULO_ORIGEM.get(a.origem, '?')}",
            f"arquivo: {a.arquivo or '?'}",
        ]
        if a.plugin_id:
            linhas.append(f"plugin: {a.plugin_id}")
        if a.duplicado:
            linhas.append("[yellow]duplicado: outra ação usa a mesma combinação[/yellow]")
        if a.origem == "gerenciador":
            linhas.append("[green]gerenciado em ~/.config/hypr/omarchy-manager-bindings.lua[/green]")
        texto.update("\n".join(linhas))
        pode = bool(a.comando) and not a.submap
        editar.disabled = not pode
        editar.tooltip = None if pode else "Sem comando descoberto ou dentro de submap: não dá para regravar com segurança."

    # Edição

    def _status(self, texto: str, classe: str = "") -> None:
        rotulo = self.query_one("#atalhos-status", Label)
        rotulo.update(texto)
        rotulo.set_classes(classe)

    @on(Button.Pressed, "#btn-editar")
    def action_editar(self) -> None:
        a = self.atalho_selecionado()
        if a is None:
            return
        if not a.comando or a.submap:
            self.app.push_screen(Aviso("Não editável", "Este atalho não tem comando descoberto ou está em um submap."))
            return
        self.app.push_screen(CapturaTecla(a), lambda c: self._capturada(a, c) if c else None)

    def _capturada(self, a: Atalho, nova: Combinacao) -> None:
        atual = Combinacao(a.modmask, a.key, a.keycode)
        if nova.chave_conflito == atual.chave_conflito:
            self.app.notify("A combinação é a mesma de antes.", severity="warning")
            return
        usos = [u for u in self.app.hyprland.usos(nova, self.atalhos) if u is not a]
        if usos:
            quem = "\n".join(f"  • {u.description or u.comando or u.combinacao}" for u in usos)
            self.app.push_screen(
                Confirmacao(
                    f"{nova.canonica}: já usado",
                    f"Já usado por:\n{quem}\n\nSubstituir? O atalho antigo deixa de funcionar e passa a ser gerenciado aqui.",
                    confirmar="Substituir",
                    perigo=True,
                ),
                lambda ok: self._gravar(a, nova) if ok else None,
            )
        else:
            self.app.push_screen(
                Confirmacao(
                    f"{nova.canonica}: livre",
                    f"Trocar [b]{a.description or a.comando}[/b]\nde {a.combinacao}\npara {nova.canonica}?\n\n"
                    "Um backup é feito e a mudança é desfeita sozinha se o Hyprland acusar erro.",
                    confirmar="Gravar",
                ),
                lambda ok: self._gravar(a, nova) if ok else None,
            )

    def _gravar(self, a: Atalho, nova: Combinacao) -> None:
        kind = "lua" if a.comando.startswith("hl.dsp.") else "exec"
        overrides = self.app.overrides.atuais()
        antiga = Combinacao(a.modmask, a.key, a.keycode).canonica
        overrides = [o for o in overrides if o.combinacao not in (antiga, nova.canonica)]
        overrides.append(Override("unbind", antiga))
        overrides.append(Override("bind", nova.canonica, a.description, a.comando, kind))
        self._status("Gravando e recarregando o Hyprland…")
        self._aplicar(overrides)

    @work(thread=True, exclusive=True, group="atalhos-acao")
    def _aplicar(self, overrides: list[Override]) -> None:
        try:
            self.app.overrides.aplicar(overrides)
        except ErroAplicacao as exc:
            msg = "Hyprland acusou erro; " + ("a alteração foi desfeita." if exc.restaurado else "NÃO foi possível restaurar, veja o log.")
            self.app.call_from_thread(self.app.notify, f"{msg}\n{exc}", severity="error", timeout=10)
        except (ErroOverrides, OSError, ValueError) as exc:
            self.app.call_from_thread(self.app.notify, f"Falha ao gravar: {exc}", severity="error", timeout=8)
        else:
            self.app.call_from_thread(self.app.notify, "Atalho gravado e Hyprland recarregado sem erros.")
        self.app.call_from_thread(self.recarregar)

    @on(Button.Pressed, "#btn-desfazer")
    def action_desfazer(self) -> None:
        if not self.app.overrides.backups():
            self.app.notify("Não há alteração para desfazer.", severity="warning")
            return
        self.app.push_screen(
            Confirmacao("Desfazer", "Voltar ao estado anterior dos atalhos gerenciados e recarregar o Hyprland?", confirmar="Desfazer"),
            lambda ok: self._desfazer() if ok else None,
        )

    @work(thread=True, exclusive=True, group="atalhos-acao")
    def _desfazer(self) -> None:
        try:
            self.app.overrides.desfazer()
        except (ErroOverrides, OSError) as exc:
            self.app.call_from_thread(self.app.notify, f"Falha ao desfazer: {exc}", severity="error", timeout=8)
        else:
            self.app.call_from_thread(self.app.notify, "Última alteração desfeita.")
        self.app.call_from_thread(self.recarregar)

    @on(Button.Pressed, "#btn-atualizar-atalhos")
    def _btn_atualizar(self) -> None:
        self.recarregar()

    # Busca, filtros e navegação

    def action_buscar(self) -> None:
        self.query_one("#atalhos-busca", Input).focus()

    def action_limpar(self) -> None:
        busca = self.query_one("#atalhos-busca", Input)
        mudou = False
        if busca.value:
            busca.value = ""
            mudou = True
        if self.filtro_plugin:
            self.filtro_plugin = ""
            mudou = True
        if mudou:
            self._renderizar()
        self.query_one("#atalhos-tabela", DataTable).focus()

    @on(Input.Changed, "#atalhos-busca")
    def _busca_mudou(self, ev: Input.Changed) -> None:
        self._filtro = ev.value.strip()
        self._renderizar()

    @on(Input.Submitted, "#atalhos-busca")
    def _busca_enter(self) -> None:
        self.query_one("#atalhos-tabela", DataTable).focus()

    @on(Select.Changed, "#atalhos-origem")
    def _origem_mudou(self, ev: Select.Changed) -> None:
        self._origem = str(ev.value) if ev.value is not Select.BLANK else "todas"
        self._renderizar()

    def action_cursor_baixo(self) -> None:
        self.query_one("#atalhos-tabela", DataTable).action_cursor_down()

    def action_cursor_cima(self) -> None:
        self.query_one("#atalhos-tabela", DataTable).action_cursor_up()
