"""Aba Plugins: tabela compacta, legenda por hover, ligar/desligar, GitHub,
desinstalar com confirmação e salto para os atalhos do plugin."""

from __future__ import annotations

import shutil

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.coordinate import Coordinate
from textual.widgets import Button, DataTable, Input, Label, Static

from omarchy_manager.models import Plugin
from omarchy_manager.services.executor import abrir_desanexado
from omarchy_manager.services.omarchy import ErroOmarchy
from omarchy_manager.ui.dialogs import Aviso, Confirmacao
from omarchy_manager.ui.navegacao import NavegacaoMixin

TIPOS_PT = {"bar-widget": "widget da barra", "service": "serviço", "panel": "painel", "overlay": "sobreposição", "bar": "barra", "menu": "menu"}
AVISO_SANDBOX = "Plugins do Omarchy Shell executam código sem sandbox dentro da sua sessão."


def legenda(p: Plugin) -> str:
    linhas = [f"[b]{p.name}[/b]  ({p.id})"]
    if p.nome_original and p.nome_original != p.name:
        linhas.append(f"[dim]nome original: {p.nome_original}[/dim]")
    linhas.append(p.description or "[i]sem descrição no manifesto[/i]")
    autor = p.author or "autor não informado"
    versao = p.version or "versão não informada"
    linhas.append(f"{autor}, {versao}")
    linhas.append("tipos: " + (", ".join(TIPOS_PT.get(k, k) for k in p.kinds) or "?"))
    linhas.append("origem: " + ("Omarchy (nativo)" if p.first_party else "terceiros"))
    if p.cloned_from:
        linhas.append(f"clonado de {p.cloned_from}")
    linhas.append("repositório: " + (p.repository_url or "não encontrado"))
    if p.metadados_incompletos:
        linhas.append("[yellow]metadados ausentes: " + ", ".join(p.metadados_incompletos) + "[/yellow]")
    if p.terceiro:
        linhas.append(f"[yellow]{AVISO_SANDBOX}[/yellow]")
    return "\n".join(linhas)


class AbaPlugins(NavegacaoMixin, Vertical):
    DEFAULT_CSS = """
    AbaPlugins { height: 1fr; }
    #plugins-topo { height: 3; }
    #plugins-busca { width: 1fr; }
    #plugins-corpo { height: 1fr; }
    #plugins-tabela { width: 2fr; }
    #plugins-detalhe {
        width: 1fr; min-width: 30; padding: 0 1; border-left: solid $panel;
    }
    #plugins-acoes { height: 3; }
    #plugins-acoes Button { margin-right: 1; min-width: 12; }
    #plugins-status { height: 1; color: $text-muted; }
    """
    TITULO_AJUDA = "Plugins"
    RODAPE = ('alternar', 'desinstalar', 'github', 'buscar')
    BINDINGS = [
        Binding("slash", "buscar", "Pesquisar", key_display="/"),
        Binding("j", "cursor_baixo", "Descer na lista", show=False),
        Binding("k", "cursor_cima", "Subir na lista", show=False),
        Binding("space", "alternar", "Ligar/Desligar"),
        Binding("g", "github", "GitHub"),
        Binding("a", "atalhos", "Atalhos"),
        Binding("d", "desinstalar", "Desinstalar"),
        Binding("c", "compartilhar", "Compartilhar"),
        Binding("escape", "limpar_busca", "Limpar a pesquisa", show=False),
    ]

    def action_compartilhar(self) -> None:
        p = self.plugin_selecionado()
        if p is None:
            return
        if not p.desinstalavel:
            self.app.push_screen(Aviso("Não compartilhável", "Só plugins de terceiros instalados em ~/.config/omarchy/plugins podem ser compartilhados."))
            return
        from omarchy_manager.services.bundle import ler_manifesto_de_pasta
        from omarchy_manager.ui.share import Compartilhar

        licenca = str(ler_manifesto_de_pasta(p.path).get("license", "") or "")
        self.app.push_screen(Compartilhar("plugin", p.id, p.name, p.path, versao=p.version, autor=p.author, licenca=licenca, origem=p.repository_url))

    def __init__(self) -> None:
        super().__init__()
        self.plugins: list[Plugin] = []
        self._por_linha: dict[str, Plugin] = {}
        self._filtro = ""

    def compose(self) -> ComposeResult:
        with Horizontal(id="plugins-topo"):
            yield Input(placeholder="Pesquisar plugin por nome, id ou tipo  (/)", id="plugins-busca")
        with Horizontal(id="plugins-corpo"):
            tabela = DataTable(id="plugins-tabela", cursor_type="row", zebra_stripes=True)
            tabela.add_columns("Estado", "Nome", "Descrição", "Tipo", "Origem", "Versão")
            yield tabela
            yield Static("Selecione um plugin.", id="plugins-detalhe")
        with Horizontal(id="plugins-acoes"):
            yield Button("Ligar", id="btn-alternar", variant="primary")
            yield Button("Atalhos", id="btn-atalhos")
            yield Button("GitHub", id="btn-github")
            yield Button("Desinstalar", id="btn-desinstalar", variant="error")
            yield Button("Compartilhar", id="btn-compartilhar")
            yield Button("Atualizar", id="btn-atualizar")
        yield Label("", id="plugins-status")

    def on_mount(self) -> None:
        self.recarregar()

    # Carga

    def recarregar(self) -> None:
        self._status("Carregando plugins…")
        self._carregar()

    @work(thread=True, exclusive=True, group="plugins-carga")
    def _carregar(self) -> None:
        try:
            brutos = self.app.omarchy.plugin_list_json()
            plugins = self.app.catalogo.listar(brutos)
        except ErroOmarchy as exc:
            self.app.call_from_thread(self._status, str(exc), "erro")
            return
        self.app.call_from_thread(self._preencher, plugins)

    def _preencher(self, plugins: list[Plugin]) -> None:
        self.plugins = plugins
        self._renderizar()
        self._status(f"{len(plugins)} plugins descobertos, {sum(p.enabled for p in plugins)} ligados")

    def _renderizar(self) -> None:
        tabela = self.query_one("#plugins-tabela", DataTable)
        selecionado = self.plugin_selecionado()
        tabela.clear()
        self._por_linha.clear()
        termo = self._filtro.lower()
        for p in self.plugins:
            if termo and termo not in f"{p.name} {p.nome_original} {p.id} {p.tipo_legivel} {p.description}".lower():
                continue
            descricao = p.description if len(p.description) <= 60 else p.description[:59].rstrip() + "…"
            tabela.add_row(
                "ligado" if p.enabled else "desligado",
                p.name,
                descricao,
                TIPOS_PT.get(p.tipo_legivel, ", ".join(TIPOS_PT.get(k, k) for k in p.kinds) or "?"),
                "Omarchy" if p.first_party else "terceiros",
                p.version or "?",
                key=p.id,
            )
            self._por_linha[p.id] = p
        if selecionado and selecionado.id in self._por_linha:
            tabela.move_cursor(row=tabela.get_row_index(selecionado.id))
        self._atualizar_detalhe()

    # Seleção e hover

    def plugin_selecionado(self) -> Plugin | None:
        tabela = self.query_one("#plugins-tabela", DataTable)
        if tabela.row_count == 0 or tabela.cursor_row is None:
            return None
        try:
            chave = tabela.coordinate_to_cell_key(Coordinate(tabela.cursor_row, 0)).row_key.value
        except Exception:
            return None
        return self._por_linha.get(chave)

    @on(DataTable.RowHighlighted, "#plugins-tabela")
    def _linha_mudou(self) -> None:
        self._atualizar_detalhe()

    @on(DataTable.RowSelected, "#plugins-tabela")
    def _linha_ativada(self) -> None:
        self.action_alternar()

    def on_mouse_move(self) -> None:
        tabela = self.query_one("#plugins-tabela", DataTable)
        coord = tabela.hover_coordinate
        tooltip = None
        if coord is not None and coord.row >= 0 and coord.column == 1 and tabela.row_count:
            try:
                chave = tabela.coordinate_to_cell_key(coord).row_key.value
            except Exception:
                chave = None
            if chave in self._por_linha:
                tooltip = legenda(self._por_linha[chave])
        if tabela.tooltip != tooltip:
            tabela.tooltip = tooltip

    def _atualizar_detalhe(self) -> None:
        p = self.plugin_selecionado()
        detalhe = self.query_one("#plugins-detalhe", Static)
        alternar = self.query_one("#btn-alternar", Button)
        github = self.query_one("#btn-github", Button)
        desinstalar = self.query_one("#btn-desinstalar", Button)
        atalhos = self.query_one("#btn-atalhos", Button)
        if p is None:
            detalhe.update("Nenhum plugin selecionado.")
            for b in (alternar, github, desinstalar, atalhos):
                b.disabled = True
            return
        detalhe.update(legenda(p))
        alternar.label = "Desligar" if p.enabled else "Ligar"
        alternar.disabled = p.enabled and not p.can_disable
        alternar.tooltip = "Este plugin não pode ser desligado." if alternar.disabled else None
        github.disabled = not p.repository_url
        github.tooltip = None if p.repository_url else "Nenhuma URL de repositório foi encontrada."
        desinstalar.disabled = not p.desinstalavel
        desinstalar.tooltip = (
            None if p.desinstalavel else "Plugins nativos do Omarchy não podem ser desinstalados; só desligados."
        )
        atalhos.disabled = False
        atalhos.tooltip = "Mostrar os atalhos associados na aba Atalhos."

    # Ações

    def _status(self, texto: str, classe: str = "") -> None:
        rotulo = self.query_one("#plugins-status", Label)
        rotulo.update(texto)
        rotulo.set_classes(classe)

    @on(Button.Pressed, "#btn-atualizar")
    def _btn_atualizar(self) -> None:
        self.recarregar()

    @on(Button.Pressed, "#btn-compartilhar")
    def _btn_compartilhar(self) -> None:
        self.action_compartilhar()

    @on(Button.Pressed, "#btn-alternar")
    def action_alternar(self) -> None:
        p = self.plugin_selecionado()
        if p is None:
            return
        if p.enabled and not p.can_disable:
            self.app.push_screen(Aviso("Não é possível desligar", f"{p.name} é obrigatório para o Omarchy Shell."))
            return
        self._status(("Desligando " if p.enabled else "Ligando ") + p.name + "…")
        self._executar_alternancia(p)

    @work(thread=True, exclusive=True, group="plugins-acao")
    def _executar_alternancia(self, p: Plugin) -> None:
        r = self.app.omarchy.plugin_disable(p.id) if p.enabled else self.app.omarchy.plugin_enable(p.id)
        verbo = "desligado" if p.enabled else "ligado"
        if r.ok:
            self.app.call_from_thread(self.app.notify, f"{p.name} {verbo}.")
        else:
            self.app.call_from_thread(self.app.notify, f"Falha ao alterar {p.name}: {r.erro_legivel}", severity="error", timeout=8)
        self.app.call_from_thread(self.recarregar)

    @on(Button.Pressed, "#btn-github")
    def action_github(self) -> None:
        p = self.plugin_selecionado()
        if p is None or not p.repository_url:
            self.app.notify("Nenhuma URL de repositório válida para este plugin.", severity="warning")
            return
        abridor = shutil.which("xdg-open") or shutil.which("omarchy-launch-browser")
        if not abridor:
            self.app.push_screen(Aviso("Sem navegador", f"Nenhum abridor encontrado. URL: {p.repository_url}"))
            return
        abrir_desanexado([abridor, p.repository_url])
        self.app.notify(f"Abrindo {p.repository_url}")

    @on(Button.Pressed, "#btn-atalhos")
    def action_atalhos(self) -> None:
        p = self.plugin_selecionado()
        if p is not None:
            self.app.ir_para_atalhos_do_plugin(p.id)

    @on(Button.Pressed, "#btn-desinstalar")
    def action_desinstalar(self) -> None:
        p = self.plugin_selecionado()
        if p is None:
            return
        if not p.desinstalavel:
            self.app.push_screen(
                Aviso("Não é possível desinstalar", f"{p.name} é um plugin nativo do Omarchy. Ele pode ser desligado, não removido.")
            )
            return

        def depois(confirmado: bool | None) -> None:
            if confirmado:
                self._status(f"Removendo {p.name}…")
                self._executar_remocao(p)

        self.app.push_screen(
            Confirmacao(
                "Desinstalar plugin",
                f"Remover [b]{p.name}[/b] ({p.id}) de {p.path}?\n\nIsso apaga a pasta do plugin. Não há desfazer automático.",
                confirmar="Desinstalar",
                perigo=True,
            ),
            depois,
        )

    @work(thread=True, exclusive=True, group="plugins-acao")
    def _executar_remocao(self, p: Plugin) -> None:
        r = self.app.omarchy.plugin_remove(p.id, confirmado=True)
        if r.ok:
            self.app.call_from_thread(self.app.notify, f"{p.name} removido.")
        else:
            self.app.call_from_thread(self.app.notify, f"Falha ao remover {p.name}: {r.erro_legivel}", severity="error", timeout=8)
        self.app.call_from_thread(self.recarregar)

    # Busca e navegação

    def action_buscar(self) -> None:
        self.query_one("#plugins-busca", Input).focus()

    def action_limpar_busca(self) -> None:
        busca = self.query_one("#plugins-busca", Input)
        if busca.value:
            busca.value = ""
        self.query_one("#plugins-tabela", DataTable).focus()

    @on(Input.Changed, "#plugins-busca")
    def _busca_mudou(self, ev: Input.Changed) -> None:
        self._filtro = ev.value.strip()
        self._renderizar()

    @on(Input.Submitted, "#plugins-busca")
    def _busca_enter(self) -> None:
        self.query_one("#plugins-tabela", DataTable).focus()

    def action_cursor_baixo(self) -> None:
        self.query_one("#plugins-tabela", DataTable).action_cursor_down()

    def action_cursor_cima(self) -> None:
        self.query_one("#plugins-tabela", DataTable).action_cursor_up()
