"""Aba Compartilhar: oferecer plugins, temas, pastas e arquivos a outra pessoa da rede local, ou ver e baixar o que ela oferece.

Nada é exposto por padrão: só o que for marcado, e só depois de a pessoa que oferece aprovar cada conexão.
"""

from __future__ import annotations

import threading
from pathlib import Path

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, DataTable, Input, Label, Static

from omarchy_manager.services import caminhos, rede, recebidos
from omarchy_manager.services.bundle import ErroBundle, extrair_para_temporario, ler_manifesto_de_pasta
from omarchy_manager.services.lan_share import ErroLan
from omarchy_manager.services.log import logger
from omarchy_manager.services.oferta import ESPERA_APROVACAO, Catalogo, ClienteOferta, ServidorOferta, arquivo_sensivel
from omarchy_manager.ui.dialogs import CSS_DIALOGO, Aviso, Confirmacao, Dialogo
from omarchy_manager.ui.navegacao import COMUM, FINAL, NavegacaoMixin
from omarchy_manager.ui.share import RevisarBundle

PORTA_PADRAO = "8765"
TIPOS = {"plugin": "plugin", "tema": "tema", "pasta": "pasta", "arquivo": "arquivo"}


def _tamanho(n: int) -> str:
    return f"{n / 1024 / 1024:.1f} MiB" if n >= 1024 * 1024 else f"{n / 1024:.0f} KiB"


class PedirCaminho(Dialogo):
    """Pede o caminho de uma pasta ou arquivo. Devolve o texto digitado, ou None."""

    DICA = "Enter adicionar · Tab muda de campo · Esc cancelar"
    FOCO_INICIAL = "#caminho"
    DEFAULT_CSS = CSS_DIALOGO + "PedirCaminho { align: center middle; } PedirCaminho #caixa { width: 80; }"
    BINDINGS = [Binding("escape", "cancelar", "Cancelar", priority=True)]

    def __init__(self, titulo: str, dica: str) -> None:
        super().__init__()
        self._titulo, self._dica = titulo, dica

    def compose(self) -> ComposeResult:
        with Vertical(id="caixa"):
            yield Label(self._titulo, classes="titulo")
            yield Static(self._dica)
            yield Input(placeholder="/caminho/completo ou ~/pasta", id="caminho")
            with Horizontal(id="botoes"):
                yield Button("Cancelar", id="cancelar")
                yield Button("Adicionar", id="ok", variant="primary")

    @on(Input.Submitted)
    def _enviado(self) -> None:
        self.dismiss(self.query_one("#caminho", Input).value.strip() or None)

    def on_button_pressed(self, ev: Button.Pressed) -> None:
        self.dismiss(self.query_one("#caminho", Input).value.strip() or None if ev.button.id == "ok" else None)

    def action_cancelar(self) -> None:
        self.dismiss(None)


class ListaRemota(Dialogo):
    """O que a outra pessoa oferece. Espaço marca; devolve a lista de ids marcados, ou None."""

    DICA = "↑/↓ ou j/k escolher · Espaço marcar · ←/→ botões · Enter confirmar · Esc cancelar"
    FOCO_INICIAL = "#remota"
    DEFAULT_CSS = CSS_DIALOGO + """
    ListaRemota #caixa { width: 90; }
    ListaRemota DataTable { height: 14; }
    """
    BINDINGS = [Binding("escape", "cancelar", "Cancelar", priority=True), Binding("space", "marcar", "Marcar", priority=True)]

    def __init__(self, itens: list[dict], origem: str) -> None:
        super().__init__()
        self._itens, self._origem = itens, origem
        self._marcados: set[str] = set()

    def compose(self) -> ComposeResult:
        with Vertical(id="caixa"):
            yield Label(f"{self._origem} oferece {len(self._itens)} item(ns)", classes="titulo")
            t = DataTable(id="remota", cursor_type="row", zebra_stripes=True)
            t.add_columns("", "Tipo", "Nome", "Tamanho")
            yield t
            yield Static("Plugin e tema baixados passam pela revisão antes de instalar. Pasta e arquivo vão para ~/Downloads/omarchy-manager/.", classes="mudo")
            with Horizontal(id="botoes"):
                yield Button("Cancelar", id="cancelar")
                yield Button("Baixar marcados", id="ok", variant="primary")

    def on_mount(self) -> None:
        super().on_mount()
        t = self.query_one("#remota", DataTable)
        for i in self._itens:
            t.add_row("[ ]", i["tipo"], i["nome"], _tamanho(i["tamanho"]), key=i["id"])

    def action_marcar(self) -> None:
        t = self.query_one("#remota", DataTable)
        if t.row_count == 0:
            return
        chave = self._itens[t.cursor_row]["id"]
        self._marcados ^= {chave}
        t.update_cell(chave, t.ordered_columns[0].key, "[x]" if chave in self._marcados else "[ ]")

    def on_button_pressed(self, ev: Button.Pressed) -> None:
        self.dismiss([i["id"] for i in self._itens if i["id"] in self._marcados] if ev.button.id == "ok" else None)

    def action_cancelar(self) -> None:
        self.dismiss(None)


class AbaCompartilhar(NavegacaoMixin, VerticalScroll):
    DEFAULT_CSS = """
    AbaCompartilhar { height: 1fr; }
    AbaCompartilhar .secao { color: $accent; text-style: bold; height: 1; margin-top: 1; }
    AbaCompartilhar .dica { color: $text-muted; height: auto; }
    AbaCompartilhar .linha { height: 3; }
    AbaCompartilhar .linha Label { width: 12; padding-top: 1; }
    AbaCompartilhar .linha Input { width: 26; }
    AbaCompartilhar #comp-porta { width: 14; }
    AbaCompartilhar #comp-porta-estado { padding: 1 0 0 2; }
    /* Verde e vermelho fixos: em temas cujo "verde" é avermelhado, as cores do tema não distinguem livre de ocupada. */
    AbaCompartilhar #comp-porta.livre, AbaCompartilhar #comp-porta.livre:focus { border: tall #3fb950; }
    AbaCompartilhar #comp-porta.ocupada, AbaCompartilhar #comp-porta.ocupada:focus { border: tall #f85149; }
    AbaCompartilhar #comp-porta-estado.livre { color: #3fb950; }
    AbaCompartilhar #comp-porta-estado.ocupada { color: #f85149; }
    AbaCompartilhar .botoes { height: auto; }
    AbaCompartilhar .botoes Button { margin-right: 1; }
    AbaCompartilhar #comp-oferta-info { height: auto; color: $success; }
    AbaCompartilhar #comp-status { height: auto; margin-top: 1; }
    """
    SECOES = (("#comp-ips",), ("#comp-porta",), ("#comp-itens", "#comp-pasta", "#comp-arquivo", "#comp-oferecer"),
              ("#comp-dest-ip", "#comp-dest-porta", "#comp-receber"))
    TITULO_AJUDA = "Compartilhar"
    AJUDA = COMUM + """
[b]Itens[/b]
  Espaço ou Enter      marca ou desmarca
  p / f                adicionar pasta / arquivo
[b]Ações[/b]
  o                    oferecer ou parar
  r                    ver o que a outra pessoa oferece
""" + FINAL
    BINDINGS = [
        Binding("j", "cursor_baixo", "Descer", show=False),
        Binding("k", "cursor_cima", "Subir", show=False),
        Binding("space", "marcar", "Marca"),
        Binding("p", "pasta", "Pasta"),
        Binding("f", "arquivo", "Arquivo"),
        Binding("o", "oferecer", "Oferecer"),
        Binding("r", "receber", "Receber"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._ips: list[rede.IpLocal] = []
        self._candidatos: list[tuple[str, str, str, Path, dict]] = []  # tipo, ident, nome, pasta, meta
        self._extras: list[tuple[str, Path]] = []  # pasta/arquivo escolhidos à mão
        self._linhas: list[str] = []  # chave de cada linha da tabela de itens
        self._marcados: dict[str, str] = {}  # chave -> id no catálogo
        self.catalogo = Catalogo()
        self.servidor: ServidorOferta | None = None
        self._cliente: ClienteOferta | None = None
        self._fila: list[dict] = []

    # ------------------------------------------------------------ montagem

    def compose(self) -> ComposeResult:
        yield Static("1. Seus IPs (escolha com ↑/↓ qual usar)", classes="secao")
        ips = DataTable(id="comp-ips", cursor_type="row", zebra_stripes=True)
        ips.add_columns("Interface", "Tipo", "IP")
        ips.styles.height = 6  # o CSS do app (DataTable 1fr) vence o DEFAULT_CSS
        yield ips
        yield Static("2. Porta para escutar", classes="secao")
        with Horizontal(classes="linha"):
            yield Input(value=PORTA_PADRAO, id="comp-porta", restrict=r"[0-9]*", max_length=5)
            yield Static("", id="comp-porta-estado")
        yield Static("3. O que oferecer (Espaço ou Enter marca; nada sai sem marcar)", classes="secao")
        itens = DataTable(id="comp-itens", cursor_type="row", zebra_stripes=True)
        itens.add_columns("", "Tipo", "Nome", "Detalhe")
        itens.styles.height = 10
        yield itens
        with Horizontal(classes="botoes"):
            yield Button("Adicionar pasta", id="comp-pasta")
            yield Button("Adicionar arquivo", id="comp-arquivo")
            yield Button("Oferecer", id="comp-oferecer", variant="primary")
        yield Static("", id="comp-oferta-info")
        yield Static("4. Receber de outra pessoa", classes="secao")
        with Horizontal(classes="linha"):
            yield Label("IP dela")
            yield Input(placeholder="192.168.0.20", id="comp-dest-ip")
            yield Label("  Porta", id="comp-dest-rotulo")
            yield Input(placeholder=PORTA_PADRAO, id="comp-dest-porta", restrict=r"[0-9]*", max_length=5)
        with Horizontal(classes="botoes"):
            yield Button("Ver o que ela oferece", id="comp-receber")
        yield Static("Cada conexão precisa ser aprovada por quem oferece, com o código de 6 palavras igual nos dois lados.", classes="dica")
        yield Static("", id="comp-status")

    def on_mount(self) -> None:
        self._app = self.app
        self.recarregar()
        self.set_interval(5, self._conferir_validade)

    def on_show(self) -> None:
        self._validar_porta()

    def action_buscar(self) -> None:
        pass

    def recarregar(self) -> None:
        self._ips = rede.ips_locais()
        tabela = self.query_one("#comp-ips", DataTable)
        tabela.clear()
        for i in self._ips:
            tabela.add_row(i.interface, i.tipo, i.ip, key=i.ip)
        if not self._ips:
            self._status("Nenhum IP de rede encontrado (sem conexão, ou o comando `ip` não existe).", "aviso")
        self._candidatos = []
        try:
            for p in self.app.catalogo.listar(self.app.omarchy.plugin_list_json()):
                if p.terceiro and p.path is not None:
                    meta = dict(versao=p.version, autor=p.author, origem=p.repository_url,
                                licenca=str(ler_manifesto_de_pasta(p.path).get("license", "") or ""))
                    self._candidatos.append(("plugin", p.id, p.name, p.path, meta))
            for t in self.app.temas.listar():
                if t.do_usuario:
                    self._candidatos.append(("tema", t.slug, t.nome, t.path, {}))
        except Exception as exc:  # lista de plugins ou temas indisponível não derruba a aba
            logger.warning("compartilhar: não foi possível listar plugins e temas: %s", exc)
        self._redesenhar_itens()
        self._validar_porta()

    def _redesenhar_itens(self) -> None:
        tabela = self.query_one("#comp-itens", DataTable)
        cursor = tabela.cursor_row
        tabela.clear()
        self._linhas = []
        for tipo, ident, nome, pasta, _ in self._candidatos:
            self._linha(tabela, f"{tipo}:{pasta}", tipo, nome, ident)
        for tipo, caminho in self._extras:
            self._linha(tabela, f"{tipo}:{caminho}", tipo, caminho.name, str(caminho))
        if self._linhas:
            tabela.move_cursor(row=min(cursor, len(self._linhas) - 1))

    def _linha(self, tabela: DataTable, chave: str, tipo: str, nome: str, detalhe: str) -> None:
        tabela.add_row("[x]" if chave in self._marcados else "[ ]", tipo, nome, detalhe, key=chave)
        self._linhas.append(chave)

    def _status(self, texto: str, classe: str = "ok") -> None:
        s = self.query_one("#comp-status", Static)
        s.set_classes(classe)
        s.update(texto)

    # ------------------------------------------------------------ teclas

    def _tabela_foco(self) -> DataTable | None:
        f = self.app.focused
        return f if isinstance(f, DataTable) else None

    def action_cursor_baixo(self) -> None:
        t = self._tabela_foco()
        if t is not None:
            t.action_cursor_down()

    def action_cursor_cima(self) -> None:
        t = self._tabela_foco()
        if t is not None:
            t.action_cursor_up()

    # ------------------------------------------------------------ seções

    def focar_entrada(self) -> None:
        self.focar_zona(2)  # o que mais se usa: a lista do que oferecer

    def acoes_do_rodape(self) -> list[str]:
        f = self.app.focused
        if isinstance(f, DataTable) and f.id == "comp-itens":
            return ["marcar", "oferecer", "pasta", "arquivo", "ajuda_aba"]
        return super().acoes_do_rodape()

    # ------------------------------------------------------------ IP e porta

    def ip_escolhido(self) -> str:
        tabela = self.query_one("#comp-ips", DataTable)
        if not self._ips or tabela.row_count == 0:
            return ""
        return self._ips[min(tabela.cursor_row, len(self._ips) - 1)].ip

    @on(DataTable.RowHighlighted, "#comp-ips")
    @on(Input.Changed, "#comp-porta")
    def _validar_porta(self, *_) -> None:
        campo = self.query_one("#comp-porta", Input)
        estado = self.query_one("#comp-porta-estado", Static)
        if self.servidor is not None:
            campo.remove_class("livre", "ocupada")
            estado.set_classes("")
            estado.update(f"em uso por esta oferta ({self.servidor.porta})")
            return
        ip = self.ip_escolhido()
        if not ip:
            campo.remove_class("livre", "ocupada")
            campo.add_class("ocupada")
            estado.set_classes("ocupada")
            estado.update("escolha um IP")
            return
        livre, motivo = rede.testar_porta(ip, campo.value)
        campo.set_class(livre, "livre")
        campo.set_class(not livre, "ocupada")
        estado.set_classes("livre" if livre else "ocupada")
        estado.update(f"{motivo} em {ip}")

    # ------------------------------------------------------------ itens marcados

    @on(DataTable.RowSelected, "#comp-itens")
    def _enter_marca(self, ev: DataTable.RowSelected) -> None:
        # O DataTable consome o Enter como RowSelected; sem isto só o Espaço marcava.
        ev.stop()
        self.action_marcar()

    def action_marcar(self) -> None:
        tabela = self.query_one("#comp-itens", DataTable)
        if self.app.focused is not tabela or not self._linhas:
            return
        chave = self._linhas[tabela.cursor_row]
        if chave in self._marcados:
            self.catalogo.remover(self._marcados.pop(chave))
        else:
            try:
                self._marcados[chave] = self._adicionar_ao_catalogo(chave).id
            except ErroBundle as exc:
                self._status(str(exc), "erro")
                return
        tabela.update_cell(chave, tabela.ordered_columns[0].key, "[x]" if chave in self._marcados else "[ ]")
        self._status(f"{len(self._marcados)} item(ns) marcado(s).", "mudo")

    def _adicionar_ao_catalogo(self, chave: str):
        tipo, _, resto = chave.partition(":")
        for t, ident, nome, pasta, meta in self._candidatos:
            if f"{t}:{pasta}" == chave:
                return (self.catalogo.adicionar_plugin if t == "plugin" else self.catalogo.adicionar_tema)(ident, nome, pasta, **meta)
        caminho = Path(resto)
        return self.catalogo.adicionar_pasta(caminho) if tipo == "pasta" else self.catalogo.adicionar_arquivo(caminho)

    def _pedir(self, tipo: str) -> None:
        titulo, dica = (("Adicionar pasta", "Caminho da pasta. Vai como pacote, sem .git, credenciais, caches e logs.")
                        if tipo == "pasta" else ("Adicionar arquivo", "Caminho do arquivo. Nomes com token, secret, credential ou chave são recusados."))

        def depois(texto: str | None) -> None:
            if not texto:
                return
            caminho = Path(texto).expanduser()
            if (tipo == "pasta" and not caminho.is_dir()) or (tipo == "arquivo" and not caminho.is_file()):
                self.app.push_screen(Aviso("Caminho inválido", f"Não encontrei {'a pasta' if tipo == 'pasta' else 'o arquivo'}:\n{caminho}"))
                return
            caminho = caminho.resolve()
            if tipo == "arquivo" and arquivo_sensivel(caminho):
                self.app.push_screen(Aviso("Arquivo recusado", f"{caminho.name} parece credencial, chave ou segredo (token, secret, credential, .env, .pem...) e não é oferecido."))
                return
            if (tipo, caminho) not in self._extras:
                self._extras.append((tipo, caminho))
            self._redesenhar_itens()
            self._status(f"{tipo.capitalize()} adicionado à lista. Marque com Espaço para oferecer.", "mudo")

        self.app.push_screen(PedirCaminho(titulo, dica), depois)

    @on(Button.Pressed, "#comp-pasta")
    def action_pasta(self) -> None:
        self._pedir("pasta")

    @on(Button.Pressed, "#comp-arquivo")
    def action_arquivo(self) -> None:
        self._pedir("arquivo")

    # ------------------------------------------------------------ oferecer

    @on(Button.Pressed, "#comp-oferecer")
    def action_oferecer(self) -> None:
        if self.servidor is not None:
            self.parar_oferta("Oferta encerrada.")
            return
        ip = self.ip_escolhido()
        if not ip:
            self._status("Escolha um IP na lista.", "erro")
            return
        if not self.catalogo.itens():
            self._status("Marque ao menos 1 item (Espaço) antes de oferecer. Nada é exposto sem marcação.", "aviso")
            return
        livre, motivo = rede.testar_porta(ip, self.query_one("#comp-porta", Input).value)
        if not livre:
            self._status(f"Porta indisponível: {motivo}.", "erro")
            return
        porta = int(self.query_one("#comp-porta", Input).value)
        self._status("Gerando certificado…", "mudo")
        self._iniciar(ip, porta)

    @work(thread=True, exclusive=True, group="oferta")
    def _iniciar(self, ip: str, porta: int) -> None:
        srv = ServidorOferta(self.catalogo, self._aprovar_conexao, ip, porta)
        try:
            srv.iniciar()
        except (ErroLan, OSError) as exc:
            self.app.call_from_thread(self._status, str(exc), "erro")
            return
        self.app.call_from_thread(self._oferta_no_ar, srv, ip)

    def _oferta_no_ar(self, srv: ServidorOferta, ip: str) -> None:
        self.servidor = srv
        self.query_one("#comp-oferecer", Button).label = "Parar de oferecer"
        self.query_one("#comp-oferta-info", Static).update(
            f"Oferecendo em {ip}:{srv.porta} por até 30 minutos, só o que está marcado.\n"
            f"Código de confirmação (tem de aparecer igual para quem conectar): {srv.codigo}"
        )
        self._status("Aguardando conexões. Cada uma pede a sua aprovação.", "mudo")
        self._validar_porta()

    def parar_oferta(self, motivo: str = "") -> None:
        srv, self.servidor = self.servidor, None
        if srv is not None:
            srv.encerrar()
        self.query_one("#comp-oferecer", Button).label = "Oferecer"
        self.query_one("#comp-oferta-info", Static).update("")
        if motivo:
            self._status(motivo, "mudo")
        self._validar_porta()

    def _conferir_validade(self) -> None:
        if self.servidor is not None and not self.servidor.ativa:
            self.parar_oferta("A oferta expirou (30 minutos).")

    def _aprovar_conexao(self, ip: str, codigo: str) -> bool:
        """Roda na thread do servidor. Abre o diálogo na interface e espera a resposta."""
        app = self._app  # `self.app` só funciona na thread da interface
        evento, resposta, tela = threading.Event(), [False], []
        nomes = [i.nome for i in self.catalogo.itens()]
        resumo = ", ".join(nomes[:6]) + (f" e mais {len(nomes) - 6}" if len(nomes) > 6 else "")

        def abrir() -> None:
            def fim(ok: bool | None) -> None:
                resposta[0] = bool(ok)
                evento.set()

            d = Confirmacao(
                "Conexão recebida",
                f"O computador [b]{ip}[/b] quer ver e baixar o que você marcou:\n{resumo or '(nada)'}\n\n"
                f"Código de confirmação:  [b]{codigo}[/b]\n"
                "Aprove só se a outra pessoa mostrar o mesmo código e esse IP for o dela.",
                confirmar="Aprovar",
            )
            tela.append(d)
            app.push_screen(d, fim)

        app.call_from_thread(abrir)
        if not evento.wait(ESPERA_APROVACAO - 2):
            app.call_from_thread(lambda: tela[0].is_attached and tela[0].dismiss(False))
        return resposta[0]

    # ------------------------------------------------------------ receber

    @on(Button.Pressed, "#comp-receber")
    def action_receber(self) -> None:
        ip = self.query_one("#comp-dest-ip", Input).value.strip()
        porta = self.query_one("#comp-dest-porta", Input).value.strip()
        if not ip or not porta.isdigit() or not 1 <= int(porta) <= 65535:
            self._status("Digite o IP e a porta (1 a 65535) da outra pessoa.", "erro")
            return
        self._cliente = ClienteOferta(ip, int(porta))
        self._status(f"Conectando a {ip}:{porta}…", "mudo")
        self._sondar(self._cliente)

    @work(thread=True, exclusive=True, group="receber-oferta")
    def _sondar(self, cli: ClienteOferta) -> None:
        try:
            codigo = cli.sondar()
        except ErroLan as exc:
            self.app.call_from_thread(self._status, str(exc), "erro")
            return
        self.app.call_from_thread(self._conferir_codigo, cli, codigo)

    def _conferir_codigo(self, cli: ClienteOferta, codigo: str) -> None:
        def depois(ok: bool | None) -> None:
            if not ok:
                self._status("Conexão cancelada. Nada foi pedido.", "aviso")
                return
            self._status("Aguardando a outra pessoa aprovar a conexão…", "mudo")
            self._autorizar(cli)

        self.app.push_screen(Confirmacao(
            "Conferir o código",
            f"Computador {cli.host}:{cli.porta}\nCódigo de confirmação:  [b]{codigo}[/b]\n\n"
            "A outra pessoa verá o mesmo código ao aprovar a sua conexão. Se for diferente, cancele.",
            confirmar="É igual, pedir conexão",
        ), depois)

    @work(thread=True, exclusive=True, group="receber-oferta")
    def _autorizar(self, cli: ClienteOferta) -> None:
        try:
            cli.autorizar()
            itens = cli.listar()
        except (ErroLan, OSError) as exc:
            self.app.call_from_thread(self._status, str(exc), "erro")
            return
        self.app.call_from_thread(self._mostrar_lista, cli, itens)

    def _mostrar_lista(self, cli: ClienteOferta, itens: list[dict]) -> None:
        if not itens:
            self._status("Conexão aprovada, mas a outra pessoa não está oferecendo nada agora.", "aviso")
            return

        def depois(ids: list[str] | None) -> None:
            if not ids:
                self._status("Nada marcado para baixar.", "aviso")
                return
            self._fila = [i for i in itens if i["id"] in ids]
            self._status(f"Baixando {len(self._fila)} item(ns)…", "mudo")
            self._baixar_fila(cli)

        self.app.push_screen(ListaRemota(itens, f"{cli.host}:{cli.porta}"), depois)

    @work(thread=True, exclusive=True, group="receber-oferta")
    def _baixar_fila(self, cli: ClienteOferta) -> None:
        pasta = caminhos.DATA_DIR / "recebidos-oferta"
        prontos: list[tuple[dict, Path, dict]] = []
        erros: list[str] = []
        for item in self._fila:
            try:
                arq, meta = cli.baixar(item["id"], pasta)
                prontos.append((item, arq, meta))
            except (ErroLan, OSError) as exc:
                erros.append(f"{item['nome']}: {exc}")
        self.app.call_from_thread(self._processar, cli, prontos, erros)

    def _processar(self, cli: ClienteOferta, prontos: list, erros: list[str]) -> None:
        self._origem = f"{cli.host}:{cli.porta}"
        self._resultados: list[str] = []
        self._erros = erros
        self._pendentes = list(prontos)
        self._proximo()

    def _proximo(self) -> None:
        if not self._pendentes:
            partes = list(self._resultados) + [f"erro em {e}" for e in self._erros]
            self._status(" | ".join(partes) or "Nada foi guardado.", "erro" if self._erros else "ok")
            return
        item, arq, meta = self._pendentes.pop(0)
        if meta["tipo"] in ("plugin", "tema"):
            self._revisar(item, arq, meta)
        else:
            self._guardar(item, arq, meta, sobrescrever=False)

    def _revisar(self, item: dict, arq: Path, meta: dict) -> None:
        try:
            pasta, man = extrair_para_temporario(arq, meta["sha256"])
            if man.tipo != meta["tipo"]:
                raise ErroBundle("o tipo do pacote não bate com o anunciado")
        except ErroBundle as exc:
            self._erros.append(f"{item['nome']}: {exc}")
            self._proximo()
            return

        def depois(destino: Path | None) -> None:
            self._resultados.append(f"{man.tipo} {man.nome} instalado desligado" if destino else f"{man.nome} não instalado")
            if destino:
                for aba in self.app.query("AbaTemas, AbaPlugins"):
                    aba.recarregar()
                self.recarregar()
            self._proximo()

        self.app.push_screen(RevisarBundle(pasta, man, self._origem), depois)

    def _guardar(self, item: dict, arq: Path, meta: dict, *, sobrescrever: bool) -> None:
        try:
            if meta["tipo"] == "pasta":
                destino = recebidos.guardar_pasta(arq, meta["sha256"], item["nome"], sobrescrever=sobrescrever)
            else:
                destino = recebidos.guardar_arquivo(arq, meta["nome"], sobrescrever=sobrescrever)
        except recebidos.JaExiste as exc:
            def depois(ok: bool | None) -> None:
                if ok:
                    self._guardar(item, arq, meta, sobrescrever=True)
                else:
                    arq.unlink(missing_ok=True)
                    self._resultados.append(f"{item['nome']} ignorado (já existia)")
                    self._proximo()

            self.app.push_screen(Confirmacao("Já existe", f"{exc.destino}\n\nSobrescrever? O antigo vai para o backup.",
                                             confirmar="Sobrescrever", perigo=True), depois)
            return
        except (ErroBundle, OSError, caminhos.CaminhoProibido) as exc:
            arq.unlink(missing_ok=True)
            self._erros.append(f"{item['nome']}: {exc}")
            self._proximo()
            return
        self._resultados.append(f"{item['nome']} em {destino}")
        self._proximo()

    def on_unmount(self) -> None:
        if self.servidor is not None:
            self.servidor.encerrar()
