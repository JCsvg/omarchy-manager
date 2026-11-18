"""Aba Webapps: a conta do Chrome de cada web app do Omarchy, a conta padrão e o cadastro de web apps novos.

Tudo vale por teclado e por mouse. As contas ficam no perfis.conf que o wrapper
omarchy-launch-webapp lê ao abrir o app (ver services/webapps.py).
"""

from __future__ import annotations

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Input, Label, OptionList, Select, Static
from textual.widgets.option_list import Option

from omarchy_manager.services import webapps as svc
from omarchy_manager.ui.dialogs import CSS_DIALOGO, Confirmacao, Dialogo
from omarchy_manager.ui.navegacao import COMUM, FINAL, NavegacaoMixin

NENHUMA = "__nenhuma__"


class EscolherConta(Dialogo):
    """Lista de contas logadas. Enter ou clique escolhe. Devolve a pasta do perfil, "" para "nenhuma", None se cancelar."""

    DICA = "↑/↓ ou j/k escolher · Enter ou clique confirma · ←/→ botões · Esc cancelar"
    FOCO_INICIAL = "#contas"
    DEFAULT_CSS = CSS_DIALOGO + "EscolherConta #caixa { width: 72; } EscolherConta OptionList { height: auto; max-height: 14; }"
    BINDINGS = [Binding("escape", "cancelar", "Cancelar", priority=True)]

    def __init__(self, titulo: str, contas: list[svc.Conta], nenhuma: str, atual: str = "") -> None:
        super().__init__()
        self._titulo, self._contas, self._nenhuma, self._atual = titulo, contas, nenhuma, atual

    def compose(self) -> ComposeResult:
        with Vertical(id="caixa"):
            yield Label(self._titulo, classes="titulo")
            if not self._contas:
                yield Static("Nenhuma conta logada encontrada no Chrome.")
            opcoes = [Option(self._nenhuma, id=NENHUMA)]
            opcoes += [Option(("● " if c.dir == self._atual else "  ") + c.rotulo, id=c.dir) for c in self._contas]
            yield OptionList(*opcoes, id="contas")
            with Horizontal(id="botoes"):
                yield Button("Cancelar", id="cancelar")
                yield Button("Escolher", id="ok", variant="primary")

    def on_mount(self) -> None:
        super().on_mount()
        lista = self.query_one("#contas", OptionList)
        for n, c in enumerate(self._contas, start=1):
            if c.dir == self._atual:
                lista.highlighted = n
                return
        lista.highlighted = 0

    def _devolver(self, id_: str | None) -> None:
        self.dismiss("" if id_ == NENHUMA else id_)

    @on(OptionList.OptionSelected)
    def _escolhida(self, ev: OptionList.OptionSelected) -> None:
        self._devolver(ev.option.id)

    def on_button_pressed(self, ev: Button.Pressed) -> None:
        if ev.button.id == "ok":
            lista = self.query_one("#contas", OptionList)
            if lista.highlighted is not None:
                self._devolver(lista.get_option_at_index(lista.highlighted).id)
        else:
            self.dismiss(None)

    def action_cancelar(self) -> None:
        self.dismiss(None)


class AdicionarWebapp(Dialogo):
    """Pede nome, link e conta (opcional). Devolve (nome, url, pasta_do_perfil ou "") ou None."""

    DICA = "Ctrl+j/k muda de campo · Enter confirma · Esc cancela"
    FOCO_INICIAL = "#wa-nome"
    DEFAULT_CSS = CSS_DIALOGO + "AdicionarWebapp #caixa { width: 80; } AdicionarWebapp .campo { margin-bottom: 1; } #wa-erro { color: $error; height: auto; }"
    BINDINGS = [Binding("escape", "cancelar", "Cancelar", priority=True)]

    def __init__(self, existentes: list[svc.Webapp], contas: list[svc.Conta]) -> None:
        super().__init__()
        self._existentes, self._contas = existentes, contas

    def compose(self) -> ComposeResult:
        with Vertical(id="caixa"):
            yield Label("Adicionar web app", classes="titulo")
            yield Label("Nome")
            yield Input(placeholder="ex.: Agenda", id="wa-nome", classes="campo")
            yield Label("Link")
            yield Input(placeholder="https://calendar.google.com", id="wa-link", classes="campo")
            yield Label("Conta (opcional; sem escolher, abre na conta padrão)")
            yield Select(
                [("Conta padrão (sem conta específica)", NENHUMA)] + [(c.rotulo, c.dir) for c in self._contas],
                value=NENHUMA, allow_blank=False, id="wa-conta", classes="campo",
            )
            yield Static("", id="wa-erro")
            with Horizontal(id="botoes"):
                yield Button("Cancelar", id="cancelar")
                yield Button("Adicionar", id="ok", variant="primary")

    @on(Input.Submitted)
    def _enviado(self) -> None:
        self._confirmar()

    def _confirmar(self) -> None:
        nome = self.query_one("#wa-nome", Input).value.strip()
        url = svc.normalizar_url(self.query_one("#wa-link", Input).value)
        erro = svc.validar_nome(nome, self._existentes) or svc.validar_url(url)
        if erro:
            self.query_one("#wa-erro", Static).update(erro)
            return
        conta = self.query_one("#wa-conta", Select).value
        self.dismiss((nome, url, "" if conta in (NENHUMA, Select.BLANK) else str(conta)))

    def on_button_pressed(self, ev: Button.Pressed) -> None:
        self._confirmar() if ev.button.id == "ok" else self.dismiss(None)

    def action_cancelar(self) -> None:
        self.dismiss(None)


class AbaWebapps(NavegacaoMixin, Vertical):
    DEFAULT_CSS = """
    AbaWebapps { height: 1fr; }
    #wa-titulo { color: $accent; text-style: bold; height: 1; }
    #wa-padrao { height: 1; }
    #wa-wrapper { height: auto; color: $warning; }
    #wa-tabela { height: 1fr; }
    #wa-botoes { height: auto; }
    #wa-botoes Button { margin-right: 1; }
    #wa-status { height: auto; }
    """
    TITULO_AJUDA = "Webapps"
    RODAPE = ("conta", "adicionar", "padrao")
    BINDINGS = [
        Binding("j", "cursor_baixo", "Descer", show=False),
        Binding("k", "cursor_cima", "Subir", show=False),
        Binding("c", "conta", "Escolher conta"),
        Binding("s", "sem_conta", "Sem conta específica", show=False),
        Binding("d", "padrao", "Conta padrão"),
        Binding("a", "adicionar", "Adicionar web app"),
        Binding("x", "remover", "Remover web app", show=False),
        Binding("i", "instalar", "Instalar wrapper", show=False),
    ]
    AJUDA = COMUM + """

[b]Nesta aba[/b]
  c ou Enter           escolher a conta da linha (Enter ou clique confirma)
  s                    linha sem conta específica (usa a conta padrão)
  d                    escolher a conta padrão (a dos web apps sem conta)
  a                    adicionar web app (nome, link, conta opcional)
  x                    remover o web app da linha
  i                    instalar o wrapper que aplica a conta
  Tudo isso também tem botão na tela e funciona com clique.
""" + FINAL

    def __init__(self) -> None:
        super().__init__()
        self._apps: list[svc.Webapp] = []
        self._contas: list[svc.Conta] = []
        self._todas: list[svc.Conta] = []

    def compose(self) -> ComposeResult:
        yield Static("Web apps e a conta do Chrome de cada um", id="wa-titulo")
        yield Static("", id="wa-padrao")
        yield Static("", id="wa-wrapper")
        tabela = DataTable(id="wa-tabela", cursor_type="row", zebra_stripes=True)
        tabela.add_columns("Web app", "Endereço", "Conta")
        yield tabela
        with Horizontal(id="wa-botoes"):
            yield Button("Escolher conta", id="wa-conta")
            yield Button("Sem conta específica", id="wa-sem")
            yield Button("Conta padrão", id="wa-padrao-btn")
            yield Button("Adicionar", id="wa-adicionar", variant="primary")
            yield Button("Remover", id="wa-remover")
            yield Button("Instalar wrapper", id="wa-instalar", variant="warning")
        yield Static("", id="wa-status")

    def on_mount(self) -> None:
        self.recarregar()

    def on_show(self) -> None:
        self.recarregar()

    def action_buscar(self) -> None:
        pass

    # leitura

    def _perfis(self) -> svc.Perfis:
        return svc.Perfis.ler()

    def _rotulo(self, pasta: str) -> str:
        for c in self._todas:
            if c.dir == pasta:
                return c.rotulo
        return f"{pasta} (conta não encontrada)"

    def recarregar(self) -> None:
        navegador = svc.navegador_padrao()
        self._contas, _ = svc.ler_contas(navegador)
        self._todas, _ = svc.ler_contas(navegador, so_logadas=False)
        self._apps = svc.listar()
        perfis = self._perfis()
        mapa, padrao = perfis.mapa(), perfis.padrao()
        tabela = self.query_one("#wa-tabela", DataTable)
        linha = tabela.cursor_row
        tabela.clear()
        for app in self._apps:
            pasta = mapa.get(app.dominio, "")
            if pasta:
                conta = Text(self._rotulo(pasta))
            else:
                conta = Text("conta padrão" if padrao else "padrão do Chrome", style="dim")
            tabela.add_row(app.nome, app.url, conta, key=app.nome)
        if self._apps:
            tabela.move_cursor(row=min(linha, len(self._apps) - 1))
        self.query_one("#wa-padrao", Static).update(
            Text(f"Conta padrão: {self._rotulo(padrao)}" if padrao else "Conta padrão: nenhuma (o Chrome escolhe)")
        )
        estado, msg = svc.estado_wrapper()
        aviso = "" if estado == "ok" else f"{msg} Aperte i para instalar."
        self.query_one("#wa-wrapper", Static).update(Text(aviso))
        self.query_one("#wa-instalar", Button).display = estado != "ok"
        if not self._apps:
            self._status("Nenhum web app. Aperte a ou clique em Adicionar.")

    def _status(self, texto: str) -> None:
        self.query_one("#wa-status", Static).update(Text(texto))

    def _selecionado(self) -> svc.Webapp | None:
        tabela = self.query_one("#wa-tabela", DataTable)
        if not self._apps or tabela.row_count == 0:
            return None
        return self._apps[tabela.cursor_row] if 0 <= tabela.cursor_row < len(self._apps) else None

    # ações

    def action_cursor_baixo(self) -> None:
        self.query_one("#wa-tabela", DataTable).action_cursor_down()

    def action_cursor_cima(self) -> None:
        self.query_one("#wa-tabela", DataTable).action_cursor_up()

    def _gravar(self, perfis: svc.Perfis) -> bool:
        try:
            perfis.gravar()
        except OSError as exc:
            self._status(f"Não foi possível gravar o perfis.conf: {exc}")
            return False
        return True

    @on(DataTable.RowSelected, "#wa-tabela")
    def _linha_escolhida(self) -> None:
        self.action_conta()

    @on(Button.Pressed, "#wa-conta")
    def action_conta(self) -> None:
        app = self._selecionado()
        if app is None:
            self._status("Escolha um web app na lista.")
            return
        atual = self._perfis().mapa().get(app.dominio, "")

        def depois(pasta: str | None) -> None:
            if pasta is None:
                return
            self._mapear(app, pasta)

        self.app.push_screen(
            EscolherConta(f"Conta de {app.nome}", self._contas, "Sem conta específica (usa a conta padrão)", atual), depois
        )

    @on(Button.Pressed, "#wa-sem")
    def action_sem_conta(self) -> None:
        app = self._selecionado()
        if app is None:
            self._status("Escolha um web app na lista.")
            return
        self._mapear(app, "")

    def _mapear(self, app: svc.Webapp, pasta: str) -> None:
        perfis = self._perfis()
        if not app.dominio:
            self._status("Este web app não tem endereço reconhecível.")
            return
        perfis.definir(app.dominio, pasta or None)
        if self._gravar(perfis):
            self.recarregar()
            self._status(f"{app.nome}: {self._rotulo(pasta)}" if pasta else f"{app.nome}: sem conta específica.")

    @on(Button.Pressed, "#wa-padrao-btn")
    def action_padrao(self) -> None:
        def depois(pasta: str | None) -> None:
            if pasta is None:
                return
            perfis = self._perfis()
            perfis.definir_padrao(pasta or None)
            if self._gravar(perfis):
                self.recarregar()
                self._status(f"Conta padrão: {self._rotulo(pasta)}" if pasta else "Sem conta padrão.")

        self.app.push_screen(
            EscolherConta("Conta padrão", self._contas, "Nenhuma (o Chrome escolhe)", self._perfis().padrao()), depois
        )

    @on(Button.Pressed, "#wa-adicionar")
    def action_adicionar(self) -> None:
        def depois(res) -> None:
            if not res:
                return
            nome, url, pasta = res
            ok, msg = svc.criar(nome, url)
            if not ok:
                self._status(f"Não foi possível criar: {msg}")
                return
            if pasta:
                perfis = self._perfis()
                perfis.definir(svc.dominio_de(url), pasta)
                self._gravar(perfis)
            self.recarregar()
            self._status(f"{nome} adicionado. {msg}")

        self.app.push_screen(AdicionarWebapp(self._apps, self._contas), depois)

    @on(Button.Pressed, "#wa-remover")
    def action_remover(self) -> None:
        app = self._selecionado()
        if app is None:
            self._status("Escolha um web app na lista.")
            return

        def depois(sim: bool | None) -> None:
            if not sim:
                return
            ok, msg = svc.remover(app.nome)
            self.recarregar()
            self._status(f"{app.nome} removido." if ok else f"Não foi possível remover: {msg}")

        self.app.push_screen(
            Confirmacao("Remover web app", f"Apagar o atalho {app.nome}? A conta escolhida fica no perfis.conf.", confirmar="Remover", perigo=True),
            depois,
        )

    @on(Button.Pressed, "#wa-instalar")
    def action_instalar(self) -> None:
        estado, msg = svc.estado_wrapper()
        if estado == "ok":
            self._status("O wrapper já está ativo.")
            return
        alvo = svc.wrapper_alvo()
        texto = {
            "ausente": f"Instalar o wrapper em {alvo}? Ele aplica a conta escolhida ao abrir cada web app.",
            "antigo": f"Atualizar {alvo}? O atual funciona, mas não conhece a conta padrão. Fica backup do atual.",
            "outro": f"{alvo} já existe e é diferente do empacotado. Substituir? Fica backup do atual.",
            "fora_do_path": f"{msg} Reinstalar não resolve; ajuste o PATH para ~/.local/bin vir antes de /usr/bin.",
        }[estado]
        if estado == "fora_do_path":
            self._status(texto)
            return

        def depois(sim: bool | None) -> None:
            if not sim:
                return
            try:
                backup = svc.instalar_wrapper()
            except OSError as exc:
                self._status(f"Não foi possível instalar: {exc}")
                return
            self.recarregar()
            self._status("Wrapper instalado" + (f" (backup {backup.name})." if backup else "."))

        self.app.push_screen(Confirmacao("Instalar wrapper", texto, confirmar="Instalar"), depois)
