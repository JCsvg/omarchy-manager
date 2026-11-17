"""Aba Temas: lista com pesquisa, prévia de paleta, exemplo de terminal,
miniatura do fundo, imagem padrão por tema e aplicação com confirmação."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.coordinate import Coordinate
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Input, Label, OptionList, Select, Static
from textual.widgets.option_list import Option

from omarchy_manager.models import Paleta, Tema
from omarchy_manager.services.ai_launcher import IADisponivel
from rich.text import Text

from omarchy_manager.services import imagem as gerador_imagem
from omarchy_manager.services import terminal_grafico
from omarchy_manager.services.previa_ao_vivo import ctrl_pressionado
from omarchy_manager.services.temas import ResultadoAplicacao, nome_de_slug
from omarchy_manager.services.theme_preview import blocos_de_imagem
from omarchy_manager.ui.dialogs import CSS_DIALOGO, DICA_FORMULARIO, DICA_LISTA, Aviso, Confirmacao, Dialogo
from omarchy_manager.ui.imagem import ImagemTerminal

SEM_PADRAO = "__sem_padrao__"
TEXTO_PREVIA_DESLIGADA = "Prévia ao vivo desligada. v liga (aplica de verdade o tema em foco); segurar Ctrl faz o mesmo enquanto estiver pressionado."


def amostra_paleta(p: Paleta) -> str:
    ordem = ["background", "foreground", "accent", "muted", "selection", "red", "green", "yellow", "blue"]
    extras = ["orange", "cyan", "magenta"]
    linhas = []
    for chave in ordem + [e for e in extras if e in p.extras]:
        cor = getattr(p, chave, None) or p.extras.get(chave, "")
        marca = "  (ANSI)" if chave in p.ausentes else ""
        linhas.append(f"[on {cor}]      [/] {chave:<10} {cor}{marca}")
    return "\n".join(linhas)


def amostra_terminal(p: Paleta) -> str:
    bg, fg = p.background, p.foreground
    return "\n".join(
        [
            f"[{bg} on {p.accent}] ~/projetos/revoada  foot                       [/]",
            f"[{fg} on {bg}] $ git status                                   [/]",
            f"[{fg} on {bg}] [{p.green}]✔ 3 arquivos prontos[/]   [{p.yellow}]⚠ 1 aviso[/]           [/]",
            f"[{fg} on {bg}] [{p.red}]✘ erro: arquivo não encontrado[/]               [/]",
            f"[{fg} on {bg}] [{fg} on {p.selection}]texto selecionado[/]  [{p.muted}]comentário mudo[/]      [/]",
            f"[{fg} on {bg}] [{p.blue}]https://omarchy.org[/]  [{p.accent}]▌[/]                    [/]",
        ]
    )


class EscolherFundo(Dialogo):
    DICA = DICA_LISTA

    """Lista os fundos permitidos do tema. Devolve o caminho, SEM_PADRAO ou None."""

    DEFAULT_CSS = CSS_DIALOGO + """
    EscolherFundo #caixa { width: 90; }
    EscolherFundo OptionList { height: auto; max-height: 20; }
    """
    BINDINGS = [Binding("escape", "cancelar", "Cancelar")]

    def __init__(self, tema: Tema, titulo: str = "Imagem padrão") -> None:
        super().__init__()
        self.tema = tema
        self._titulo = titulo

    def compose(self) -> ComposeResult:
        with Vertical(id="caixa"):
            yield Label(f"{self._titulo}: {self.tema.nome}", classes="titulo")
            if not self.tema.fundos:
                yield Static("Este tema não tem fundos em backgrounds/ nem em ~/.config/omarchy/backgrounds/.")
            opcoes = [Option("Sem imagem padrão (deixar o Omarchy escolher)", id=SEM_PADRAO)]
            for f in self.tema.fundos:
                marca = " ●" if self.tema.fundo_padrao and f.resolve() == self.tema.fundo_padrao else ""
                opcoes.append(Option(f"{f.name}{marca}   [dim]{f.parent}[/dim]", id=str(f)))
            yield OptionList(*opcoes, id="fundos")
            with Horizontal(id="botoes"):
                yield Button("Cancelar", id="cancelar")

    def on_mount(self) -> None:
        super().on_mount()
        self.query_one(OptionList).focus()

    @on(OptionList.OptionSelected)
    def _escolhido(self, ev: OptionList.OptionSelected) -> None:
        self.dismiss(ev.option.id)

    def on_button_pressed(self) -> None:
        self.dismiss(None)

    def action_cancelar(self) -> None:
        self.dismiss(None)


class CriarTemaIA(Dialogo):
    DICA = DICA_FORMULARIO

    """IA instalada, nome do tema, tema base e diretório de trabalho."""

    DEFAULT_CSS = CSS_DIALOGO + """
    CriarTemaIA #caixa { width: 80; }
    CriarTemaIA Select, CriarTemaIA Input { margin-bottom: 1; }
    """
    BINDINGS = [Binding("escape", "cancelar", "Cancelar")]

    def __init__(self, ias: list[IADisponivel], temas: list[Tema], base_inicial: Tema | None) -> None:
        super().__init__()
        self.ias = ias
        self.temas = temas
        self.base_inicial = base_inicial

    def compose(self) -> ComposeResult:
        with Vertical(id="caixa"):
            yield Label("Criar tema com IA", classes="titulo")
            yield Static(
                "O chat abre em um terminal novo, dentro de um diretório de trabalho próprio. "
                "O agente só copia o tema para ~/.config/omarchy/themes/ depois do seu sim."
            )
            yield Label("IA")
            yield Select([(f"{d.adaptador.nome}  ({d.caminho})", d.adaptador.id) for d in self.ias], value=self.ias[0].adaptador.id, allow_blank=False, id="ia-escolha")
            yield Label("Nome do tema")
            yield Input(placeholder="ex.: Noite Serrana", id="ia-nome")
            yield Label("Tema usado como base (copiado para o workspace)")
            opcoes = [("Nenhum", "")] + [(t.nome, t.slug) for t in self.temas]
            yield Select(opcoes, value=self.base_inicial.slug if self.base_inicial else "", allow_blank=False, id="ia-base")
            yield Static("", id="ia-workspace", classes="mudo")
            with Horizontal(id="botoes"):
                yield Button("Cancelar", id="cancelar")
                yield Button("Abrir chat", id="ok", variant="primary")

    def on_mount(self) -> None:
        super().on_mount()
        self.query_one("#ia-nome", Input).focus()
        self._atualizar_workspace("")

    @on(Input.Changed, "#ia-nome")
    def _nome_mudou(self, ev: Input.Changed) -> None:
        self._atualizar_workspace(ev.value)

    def _atualizar_workspace(self, nome: str) -> None:
        from omarchy_manager.services.ai_launcher import slugificar

        ws = self.app.ia.workspaces / slugificar(nome)
        self.query_one("#ia-workspace", Static).update(f"Diretório de trabalho: {ws}")

    @on(Input.Submitted, "#ia-nome")
    def _enter(self) -> None:
        self._confirmar()

    def on_button_pressed(self, ev: Button.Pressed) -> None:
        if ev.button.id == "ok":
            self._confirmar()
        else:
            self.dismiss(None)

    def _confirmar(self) -> None:
        nome = self.query_one("#ia-nome", Input).value.strip()
        if not nome:
            self.app.notify("Dê um nome ao tema.", severity="warning")
            return
        ia_id = self.query_one("#ia-escolha", Select).value
        ia = next(d for d in self.ias if d.adaptador.id == ia_id)
        base_slug = self.query_one("#ia-base", Select).value
        base = next((t for t in self.temas if t.slug == base_slug), None) if base_slug else None
        self.dismiss((ia, nome, base))

    def action_cancelar(self) -> None:
        self.dismiss(None)


class TabelaTemas(DataTable):
    """Na lista de temas, esquerda e direita trocam o fundo exibido em vez de rolar a tabela."""

    def _aba(self) -> "AbaTemas | None":
        return next((a for a in self.ancestors if isinstance(a, AbaTemas)), None)

    def action_cursor_left(self) -> None:
        aba = self._aba()
        if aba is not None:
            aba.action_fundo_relativo(-1)

    def action_cursor_right(self) -> None:
        aba = self._aba()
        if aba is not None:
            aba.action_fundo_relativo(1)


class AbaTemas(Vertical):
    DEFAULT_CSS = """
    AbaTemas { height: 1fr; }
    #temas-topo { height: 3; }
    #temas-busca { width: 1fr; }
    #temas-corpo { height: 1fr; }
    #temas-tabela { width: 1fr; min-width: 28; max-width: 46; }
    #temas-previa { width: 3fr; layout: horizontal; border-left: solid $panel; overflow-y: hidden; }
    #previa-info { width: 54; height: 1fr; padding: 0 1; }
    #previa-imagem { width: 1fr; height: 1fr; padding: 0 1; border-left: solid $panel; }
    #previa-imagem-titulo { color: $accent; text-style: bold; height: 1; }
    #previa-foto { height: 1fr; }
    #previa-motivo { height: auto; color: $text-muted; text-style: dim; }
    AbaTemas.estreito #temas-previa { layout: vertical; overflow-y: auto; }
    AbaTemas.estreito #previa-info { width: 1fr; height: auto; }
    AbaTemas.estreito #previa-imagem { width: 1fr; height: auto; border-left: none; }
    #temas-previa .secao { color: $accent; text-style: bold; margin-top: 1; }
    #previa-modo { height: 1; }
    #previa-modo.ligada { color: $warning; text-style: bold; }
    #temas-acoes { height: 3; }
    #temas-acoes Button { margin-right: 1; min-width: 12; }
    #temas-status { height: 1; color: $text-muted; }
    """
    BINDINGS = [
        Binding("slash", "buscar", "Pesquisar", key_display="/"),
        Binding("j", "cursor_baixo", "Descer na lista", show=False),
        Binding("k", "cursor_cima", "Subir na lista", show=False),
        Binding("enter", "aplicar", "Aplicar o tema selecionado", show=False),
        Binding("shift+enter", "aplicar_fundo", "Só o fundo, sem trocar o tema", key_display="Shift+Enter"),
        Binding("h,left", "fundo_relativo(-1)", "Fundo anterior", key_display="h/←"),
        Binding("l,right", "fundo_relativo(1)", "Próximo fundo (vira o padrão)", key_display="l/→"),
        Binding("p", "fundo_padrao", "Lista de fundos"),
        Binding("v", "alternar_previa", "Prévia ao vivo"),
        Binding("escape", "limpar_busca", "Desligar a prévia ao vivo e limpar a pesquisa", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.temas: list[Tema] = []
        self._por_linha: dict[str, Tema] = {}
        self._filtro = ""
        self._cache_blocos: dict[tuple[str, int, int], object] = {}
        self._previa_ligada = False  # alternada com `v`
        self._ctrl = False  # Ctrl segurado, visto pelo Hyprland
        self._sondar = True
        self._sondando = False
        self._timer_previa = None
        self._timer_resize = None
        self._fundo_exibido: dict[str, Path] = {}  # escolha feita com h/l nesta sessão
        self._padrao_pendente: tuple[str, Path] | None = None
        self._timer_padrao = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="temas-topo"):
            yield Input(placeholder="Pesquisar tema por nome  (/)", id="temas-busca")
        with Horizontal(id="temas-corpo"):
            tabela = TabelaTemas(id="temas-tabela", cursor_type="row", zebra_stripes=True)
            tabela.add_columns(" ", "Tema", "Origem", "Modo")
            yield tabela
            with VerticalScroll(id="temas-previa"):
                with VerticalScroll(id="previa-info"):
                    yield Static("Selecione um tema.", id="previa-cabecalho")
                    yield Static("Paleta", classes="secao")
                    yield Static("", id="previa-paleta")
                    yield Static("Terminal", classes="secao")
                    yield Static("", id="previa-terminal")
                    yield Static("Fundo", classes="secao")
                    yield Static("", id="previa-fundo-info")
                with Vertical(id="previa-imagem"):
                    yield Static("Fundo do tema", id="previa-imagem-titulo")
                    yield ImagemTerminal(id="previa-foto")
                    yield Static("", id="previa-fundo")
                    yield Label("", id="previa-motivo")
        with Horizontal(id="temas-acoes"):
            yield Button("Aplicar", id="btn-aplicar", variant="primary")
            yield Button("Lista de fundos", id="btn-fundo")
            yield Button("Criar tema com IA", id="btn-ia")
            yield Button("Compartilhar", id="btn-compartilhar-tema")
            yield Button("Receber", id="btn-receber")
            yield Button("Atualizar", id="btn-atualizar-temas")
        yield Label(TEXTO_PREVIA_DESLIGADA, id="previa-modo")
        yield Label("", id="temas-status")

    def on_mount(self) -> None:
        self.recarregar()
        self.set_interval(0.25, self._tique_ctrl)

    LARGURA_DUAS_COLUNAS = 125

    def on_resize(self) -> None:
        self.set_class(self.size.width < self.LARGURA_DUAS_COLUNAS, "estreito")
        if self.has_class("estreito"):  # some já, antes de a imagem ser emitida em um espaço que mudou
            self.query_one("#previa-foto").display = False
        if self._timer_resize is not None:
            self._timer_resize.stop()
        self._timer_resize = self.set_timer(0.3, self._atualizar_previa)

    def _tamanho_miniatura(self) -> tuple[int, int]:
        """(colunas, linhas) da miniatura, na proporção 16:9 (1 célula = 1 x 2 pixels)."""
        if self.has_class("estreito"):
            colunas = max(16, min(self.size.width - 6, 72))
            linhas = 10**6
        else:
            caixa = self.query_one("#previa-imagem").size
            colunas, linhas = caixa.width - 2, caixa.height - 3
        if colunas < 16 or linhas < 4:
            return 48, 10
        linhas = max(4, min(linhas, colunas * 9 // 32))
        colunas = max(16, min(colunas, linhas * 32 // 9))
        return colunas, linhas

    # Carga

    def recarregar(self) -> None:
        self._status("Carregando temas…")
        self._carregar()

    @work(thread=True, exclusive=True, group="temas-carga")
    def _carregar(self) -> None:
        try:
            temas = self.app.temas.listar()
        except Exception as exc:  # erro de comando ou de leitura
            self.app.call_from_thread(self._status, f"Falha ao listar temas: {exc}", "erro")
            return
        self.app.call_from_thread(self._preencher, temas)

    def _preencher(self, temas: list[Tema]) -> None:
        self.temas = temas
        self._renderizar()
        atual = next((t.nome for t in temas if t.atual), "?")
        self._status(f"{len(temas)} temas, atual: {atual}")

    def _renderizar(self) -> None:
        tabela = self.query_one("#temas-tabela", DataTable)
        selecionado = self.tema_selecionado()
        tabela.clear()
        self._por_linha.clear()
        termo = self._filtro.lower()
        for t in self.temas:
            if termo and termo not in f"{t.nome} {t.slug}".lower():
                continue
            modo = "?" if t.paleta is None else ("claro" if not t.paleta.escuro else "escuro")
            tabela.add_row("●" if t.atual else " ", t.nome, "usuário" if t.do_usuario else "Omarchy", modo, key=t.slug)
            self._por_linha[t.slug] = t
        alvo = selecionado.slug if selecionado and selecionado.slug in self._por_linha else None
        if alvo is None:
            alvo = next((s for s, t in self._por_linha.items() if t.atual), None)
        if alvo is not None:
            tabela.move_cursor(row=tabela.get_row_index(alvo))
        self._atualizar_previa()

    # Seleção e prévia

    def tema_selecionado(self) -> Tema | None:
        tabela = self.query_one("#temas-tabela", DataTable)
        if tabela.row_count == 0 or tabela.cursor_row is None:
            return None
        try:
            chave = tabela.coordinate_to_cell_key(Coordinate(tabela.cursor_row, 0)).row_key.value
        except Exception:
            return None
        return self._por_linha.get(chave)

    @on(DataTable.RowHighlighted, "#temas-tabela")
    def _linha_mudou(self) -> None:
        self.gravar_padrao_pendente()  # o padrão do tema que ficou para trás não pode se perder
        self._atualizar_previa()
        if self._previa_ligada or self._ctrl:
            self._agendar_previa()

    # Prévia ao vivo: aplica o tema de verdade por um tempo e volta ao original.

    DEBOUNCE_PREVIA = 0.5

    def _tema_sob_o_mouse(self) -> Tema | None:
        tabela = self.query_one("#temas-tabela", DataTable)
        coord = tabela.hover_coordinate
        if not tabela.mouse_hover or coord is None or coord.row < 0 or coord.row >= tabela.row_count:
            return None
        try:
            return self._por_linha.get(tabela.coordinate_to_cell_key(coord).row_key.value)
        except Exception:
            return None

    def _tema_desejado(self) -> Tema | None:
        if self._ctrl:
            return self._tema_sob_o_mouse() or self.tema_selecionado()
        if self._previa_ligada:
            return self.tema_selecionado()
        return None

    def action_alternar_previa(self) -> None:
        if self._previa_ligada:
            self.encerrar_previa()
            return
        if self.tema_selecionado() is None:
            return
        self._previa_ligada = True
        self._rotulo_previa()
        self._agendar_previa(imediato=True)

    def encerrar_previa(self) -> None:
        """Desliga a prévia e volta ao tema original (Esc, `v`, troca de aba)."""
        ligada = self._previa_ligada or self._ctrl
        self._previa_ligada = False
        self._ctrl = False
        if self._timer_previa is not None:
            self._timer_previa.stop()
            self._timer_previa = None
        if ligada or self.app.previa.ativa:
            self._rotulo_previa()
            self._executar_previa(None)

    def _agendar_previa(self, imediato: bool = False) -> None:
        if self._timer_previa is not None:
            self._timer_previa.stop()
        self._timer_previa = self.set_timer(0.05 if imediato else self.DEBOUNCE_PREVIA, self._disparar_previa)

    def _disparar_previa(self) -> None:
        self._timer_previa = None
        alvo = self._tema_desejado()
        if alvo is None and not self.app.previa.ativa:
            return
        fundo = None
        if alvo is not None and (alvo.slug in self._fundo_exibido or alvo.fundo_padrao):
            fundo = self._imagem_para_previa(alvo)
        self._executar_previa(alvo.slug if alvo else None, fundo)

    @work(thread=True, group="temas-previa-viva")
    def _executar_previa(self, slug: str | None, fundo: Path | None = None) -> None:
        previa = self.app.previa
        if slug is None:
            previa.restaurar()
            mensagem = ""
        else:
            ok, mensagem = previa.iniciar(slug)
            if ok and fundo is not None:
                previa.definir_fundo(fundo)
        self.app.call_from_thread(self._previa_viva_feita, mensagem)

    def _previa_viva_feita(self, mensagem: str) -> None:
        if mensagem:
            self.app.notify(mensagem, severity="error", timeout=8)
        self.app.aplicar_paleta()
        self._rotulo_previa()
        alvo = self._tema_desejado()
        desejado = alvo.slug if alvo else None
        previa = self.app.previa
        if (desejado is None and previa.ativa) or (desejado is not None and desejado != previa.aplicado and not mensagem):
            self._agendar_previa()

    def _rotulo_previa(self) -> None:
        rotulo = self.query_one("#previa-modo", Label)
        previa = self.app.previa
        if self._previa_ligada or self._ctrl or previa.ativa:
            original = nome_de_slug(previa.tema_original) if previa.tema_original else "o tema anterior"
            como = "solte o Ctrl" if self._ctrl and not self._previa_ligada else "v ou Esc"
            rotulo.update(f"PRÉVIA AO VIVO: o tema em foco está aplicado de verdade. {como} volta para {original}. Enter mantém.")
            rotulo.set_classes("ligada")
        else:
            rotulo.update(TEXTO_PREVIA_DESLIGADA)
            rotulo.set_classes("")

    def _tique_ctrl(self) -> None:
        if not self._sondar or self._sondando or len(self.app.screen_stack) > 1:
            return
        if self.app.aba_ativa() is not AbaTemas or not getattr(self.app, "app_focus", True):
            if self._ctrl:
                self._ctrl_mudou(False)
            return
        self._sondando = True
        self._sondar_ctrl()

    @work(thread=True, group="temas-ctrl")
    def _sondar_ctrl(self) -> None:
        estado = ctrl_pressionado(self.app.hyprland)
        self.app.call_from_thread(self._ctrl_mudou, estado)

    def _ctrl_mudou(self, estado: bool | None) -> None:
        self._sondando = False
        if estado is None:
            self._sondar = False  # sem Hyprland ou sem resposta: fica só a tecla `v`
            estado = False
        if estado == self._ctrl:
            return
        self._ctrl = estado
        self._rotulo_previa()
        if estado:
            self._agendar_previa()
        elif not self._previa_ligada:
            if self._timer_previa is not None:
                self._timer_previa.stop()
                self._timer_previa = None
            if self.app.previa.ativa:
                self._executar_previa(None)

    def on_mouse_move(self) -> None:
        if self._ctrl and not self._previa_ligada:
            alvo = self._tema_sob_o_mouse()
            if alvo is not None and alvo.slug != self.app.previa.aplicado:
                self._agendar_previa()

    @on(DataTable.RowSelected, "#temas-tabela")
    def _linha_ativada(self) -> None:
        self.action_aplicar()

    def _atualizar_previa(self) -> None:
        t = self.tema_selecionado()
        cab = self.query_one("#previa-cabecalho", Static)
        pal = self.query_one("#previa-paleta", Static)
        term = self.query_one("#previa-terminal", Static)
        info = self.query_one("#previa-fundo-info", Static)
        fundo = self.query_one("#previa-fundo", Static)
        if t is None:
            cab.update("Nenhum tema selecionado.")
            for w in (pal, term, info, fundo):
                w.update("")
            return
        origem = "instalado pelo usuário" if t.do_usuario else "nativo do Omarchy"
        atual = "  [b](atual)[/b]" if t.atual else ""
        cab.update(f"[b]{t.nome}[/b]{atual}\n{origem}\n[dim]{t.path}[/dim]")
        if t.paleta is None:
            pal.update("[yellow]colors.toml ausente ou inválido; a prévia não está disponível.[/yellow]")
            term.update("")
        else:
            modo = "claro" if not t.paleta.escuro else "escuro"
            pal.update(f"modo {modo}\n" + amostra_paleta(t.paleta))
            term.update(amostra_terminal(t.paleta))
        imagem = self._imagem_para_previa(t)
        foto = self.query_one("#previa-foto", ImagemTerminal)
        motivo = self.query_one("#previa-motivo", Label)
        em_pixels = self._imagem_em_pixels() and not foto.falhou
        foto.display = em_pixels
        fundo.display = not em_pixels
        if imagem is None:
            info.update("Este tema não tem fundos.")
            fundo.update("")
            foto.mostrar(None)
            motivo.update("")
            return
        posicao = self._indice_do_fundo(t, imagem)
        pendente = self._padrao_pendente is not None and self._padrao_pendente[0] == t.slug
        if pendente:
            marca = "  [b]● padrão[/b] [dim](gravando…)[/dim]"
        elif self._indice_do_fundo(t, t.fundo_padrao) == posicao and posicao >= 0:
            marca = "  [b]● padrão[/b]"
        else:
            marca = "  [dim]sem padrão definido[/dim]"
        conta = f"{posicao + 1} de {len(t.fundos)}" if posicao >= 0 else f"{len(t.fundos)} fundo(s)"
        dica = "h/l ou ← → trocam o fundo, e o exibido vira o padrão" if len(t.fundos) > 1 else "único fundo deste tema"
        info.update(f"{imagem.name}  [b]{conta}[/b]{marca}\n[dim]{imagem}[/dim]\n[dim]{dica}[/dim]")
        if em_pixels:
            motivo.update("")
            foto.mostrar(imagem)
            return
        if self.has_class("estreito") and terminal_grafico.protocolo():
            motivo.update("Imagem em blocos: janela estreita. Alargue o terminal para ver em pixels.")
        elif foto.falhou:
            motivo.update("Imagem em blocos: a conversão para o formato do terminal falhou (ImageMagick).")
        else:
            motivo.update(terminal_grafico.motivo_blocos())
        colunas, linhas = self._tamanho_miniatura()
        chave = (str(imagem), colunas, linhas)
        if chave in self._cache_blocos:
            blocos = self._cache_blocos[chave]
            fundo.update(blocos if blocos else "[dim]prévia indisponível (ImageMagick ausente ou falhou)[/dim]")
        else:
            fundo.update("[dim]gerando prévia…[/dim]")
            self._gerar_previa(imagem, colunas, linhas)

    # Troca do fundo exibido com h/l e setas. O fundo exibido vira o padrão do tema.

    DEBOUNCE_PADRAO = 0.6

    def _indice_do_fundo(self, t: Tema, imagem: Path | None) -> int:
        if imagem is None:
            return -1
        try:
            alvo = imagem.resolve()
        except OSError:
            alvo = imagem
        for i, f in enumerate(t.fundos):
            try:
                if f.resolve() == alvo:
                    return i
            except OSError:
                continue
        return -1

    def action_fundo_relativo(self, passo: int) -> None:
        t = self.tema_selecionado()
        if t is None:
            return
        if len(t.fundos) < 2:
            self._status("Este tema não tem outro fundo para trocar." if t.fundos else "Este tema não tem fundos.")
            return
        atual = self._indice_do_fundo(t, self._imagem_para_previa(t))
        novo = t.fundos[(max(atual, 0) + passo) % len(t.fundos)] if atual >= 0 else t.fundos[0]
        self._fundo_exibido[t.slug] = novo
        self._padrao_pendente = (t.slug, novo)
        if self._timer_padrao is not None:
            self._timer_padrao.stop()
        self._timer_padrao = self.set_timer(self.DEBOUNCE_PADRAO, self._assentou)
        self._atualizar_previa()

    def _assentou(self) -> None:
        self._timer_padrao = None
        self.gravar_padrao_pendente()
        # Com a prévia ao vivo ligada, o fundo da área de trabalho acompanha o exibido.
        t = self.tema_selecionado()
        if t is not None and self.app.previa.ativa and self.app.previa.aplicado == t.slug:
            self._executar_previa(t.slug, self._imagem_para_previa(t))

    def gravar_padrao_pendente(self) -> None:
        """Grava em config.toml o padrão escolhido com h/l. Chamado ao assentar, ao mudar
        de tema, ao trocar de aba e ao sair."""
        if self._timer_padrao is not None:
            self._timer_padrao.stop()
            self._timer_padrao = None
        pendente, self._padrao_pendente = self._padrao_pendente, None
        if pendente is None:
            return
        slug, imagem = pendente
        tema = next((x for x in self.temas if x.slug == slug), None)
        if tema is None:
            return
        try:
            gravada = self.app.temas.definir_fundo_padrao(tema, imagem)
        except (ValueError, OSError) as exc:
            self.app.notify(f"Não foi possível guardar a imagem padrão de {tema.nome}: {exc}", severity="error", timeout=8)
            self._fundo_exibido.pop(slug, None)
            return
        novo = replace(tema, fundo_padrao=gravada)
        self.temas = [novo if x.slug == slug else x for x in self.temas]
        if slug in self._por_linha:
            self._por_linha[slug] = novo
        self._fundo_exibido.pop(slug, None)
        if self.is_attached:
            sel = self.tema_selecionado()
            if sel is not None and sel.slug == slug:
                self._atualizar_previa()

    def on_unmount(self) -> None:
        try:
            self.gravar_padrao_pendente()
        except Exception:
            pass

    def _imagem_para_previa(self, t: Tema) -> Path | None:
        exibido = self._fundo_exibido.get(t.slug)
        if exibido is not None and exibido.is_file():
            return exibido
        if t.fundo_padrao and t.fundo_padrao.is_file():
            return t.fundo_padrao
        return t.fundos[0] if t.fundos else None

    @work(thread=True, group="temas-previa")
    def _gerar_previa(self, imagem: Path, colunas: int, linhas: int) -> None:
        origem = gerador_imagem.intermediario(imagem) or imagem
        ansi = gerador_imagem.blocos_chafa(origem, colunas, linhas)
        if ansi is not None:
            blocos = Text.from_ansi(ansi)
        else:
            lista = blocos_de_imagem(origem, largura=colunas, altura_linhas=linhas)
            blocos = "\n".join(lista) if lista else None
        self.app.call_from_thread(self._previa_pronta, imagem, colunas, linhas, blocos)

    def _imagem_em_pixels(self) -> bool:
        return terminal_grafico.protocolo() is not None and not self.has_class("estreito")

    def _previa_pronta(self, imagem: Path, colunas: int, linhas: int, blocos) -> None:
        if len(self._cache_blocos) > 200:
            self._cache_blocos.clear()
        self._cache_blocos[(str(imagem), colunas, linhas)] = blocos
        t = self.tema_selecionado()
        if t is not None and self._imagem_para_previa(t) == imagem and (colunas, linhas) == self._tamanho_miniatura():
            self.query_one("#previa-fundo", Static).update(
                blocos if blocos else "[dim]prévia indisponível (ImageMagick ausente ou falhou)[/dim]"
            )

    # Ações

    def _status(self, texto: str, classe: str = "") -> None:
        rotulo = self.query_one("#temas-status", Label)
        rotulo.update(texto)
        rotulo.set_classes(classe)

    @on(Button.Pressed, "#btn-atualizar-temas")
    def _btn_atualizar(self) -> None:
        self._cache_blocos.clear()
        self.recarregar()

    @on(Button.Pressed, "#btn-fundo")
    def action_fundo_padrao(self) -> None:
        t = self.tema_selecionado()
        if t is None:
            return

        def depois(escolha: str | None) -> None:
            if escolha is None:
                return
            try:
                if escolha == SEM_PADRAO:
                    self.app.temas.definir_fundo_padrao(t, None)
                    self.app.notify(f"{t.nome} sem imagem padrão.")
                else:
                    gravada = self.app.temas.definir_fundo_padrao(t, Path(escolha))
                    self.app.notify(f"Imagem padrão de {t.nome}: {gravada.name}")
            except (ValueError, OSError) as exc:
                self.app.push_screen(Aviso("Imagem recusada", str(exc)))
                return
            self._fundo_exibido.pop(t.slug, None)
            self.recarregar()

        self.gravar_padrao_pendente()
        t = next((x for x in self.temas if x.slug == t.slug), t)
        self.app.push_screen(EscolherFundo(t), depois)

    @on(Button.Pressed, "#btn-compartilhar-tema")
    def action_compartilhar(self) -> None:
        t = self.tema_selecionado()
        if t is None:
            return
        if not t.do_usuario:
            self.app.push_screen(Aviso("Não compartilhável", "Só temas instalados pelo usuário (~/.config/omarchy/themes) podem ser compartilhados; os nativos já vêm com o Omarchy."))
            return
        from omarchy_manager.ui.share import Compartilhar

        self.app.push_screen(Compartilhar("tema", t.slug, t.nome, t.path))

    @on(Button.Pressed, "#btn-receber")
    def action_receber(self) -> None:
        from omarchy_manager.ui.share import Receber

        self.app.push_screen(Receber(), lambda destino: self.recarregar() if destino else None)

    @on(Button.Pressed, "#btn-ia")
    def action_criar_com_ia(self) -> None:
        disponiveis = self.app.ia.disponiveis()
        if not disponiveis:
            self.app.push_screen(
                Aviso("Nenhuma IA encontrada", "Instale Claude Code, Codex, OpenCode ou Copilot CLI e deixe no PATH.")
            )
            return
        if self.app.ia.terminal() is None:
            self.app.push_screen(Aviso("Sem terminal", "Nenhum terminal encontrado (xdg-terminal-exec, foot, alacritty, ghostty, kitty, wezterm)."))
            return

        def depois(escolha: tuple[IADisponivel, str, Tema | None] | None) -> None:
            if escolha is None:
                return
            ia, nome, base = escolha
            try:
                argv = self.app.ia.abrir(ia, nome, base.path if base else None)
            except (OSError, ValueError) as exc:
                self.app.push_screen(Aviso("Falha ao abrir o chat", str(exc)))
                return
            self.app.notify(f"Chat aberto com {ia.adaptador.nome} em {argv[1] if len(argv) > 1 else ''}", timeout=6)

        self.app.push_screen(CriarTemaIA(disponiveis, self.temas, self.tema_selecionado()), depois)

    @on(Button.Pressed, "#btn-aplicar")
    def action_aplicar(self) -> None:
        t = self.tema_selecionado()
        if t is None:
            return
        fundo = f"\nFundo padrão: {t.fundo_padrao.name}" if t.fundo_padrao else "\nSem imagem padrão definida."
        self.app.push_screen(
            Confirmacao(
                "Aplicar tema",
                f"Aplicar [b]{t.nome}[/b] em toda a área de trabalho?{fundo}\n\nIsso roda `omarchy theme set {t.slug}`.",
                confirmar="Aplicar",
            ),
            lambda ok: self._aplicar(t) if ok else None,
        )

    def action_aplicar_fundo(self) -> None:
        """Shift+Enter: usa só a imagem exibida do tema selecionado como fundo, sem trocar o tema."""
        t = self.tema_selecionado()
        if t is None:
            return
        if self.app.previa.ativa:
            self.app.notify("Desligue a prévia ao vivo (v ou Esc) antes de aplicar só o fundo.", severity="warning")
            return
        imagem = self._imagem_para_previa(t)
        if imagem is None:
            self._status(f"{t.nome} não tem imagem de fundo.", "aviso")
            return
        self._aplicar_so_fundo(imagem)

    @work(thread=True, exclusive=True, group="temas-fundo")
    def _aplicar_so_fundo(self, imagem: Path) -> None:
        resultado = self.app.omarchy.theme_bg_set(imagem)
        self.app.call_from_thread(self._fundo_aplicado, imagem, resultado)

    def _fundo_aplicado(self, imagem: Path, resultado) -> None:
        if resultado.ok:
            self.app.notify(f"Fundo trocado para {imagem.name}. O tema continua o mesmo.", timeout=5)
        else:
            self.app.notify(f"Não foi possível trocar o fundo: {resultado.erro_legivel}", severity="error", timeout=6)

    @work(thread=True, exclusive=True, group="temas-acao")
    def _aplicar(self, t: Tema) -> None:
        self.app.call_from_thread(self._status, f"Aplicando {t.nome}…")
        resultado = self.app.temas.aplicar(t)
        if resultado.tema_ok:
            self.app.previa.manter()  # aplicado de vez: não há mais o que restaurar
            self._previa_ligada = False
        self.app.call_from_thread(self._aplicado, t, resultado)

    def _aplicado(self, t: Tema, r: ResultadoAplicacao) -> None:
        self.app.notify(r.tema_msg, severity="information" if r.tema_ok else "error", timeout=6)
        if r.fundo_msg:
            sev = "information" if r.fundo_ok else ("warning" if r.fundo_ok is None else "error")
            self.app.notify(r.fundo_msg, severity=sev, timeout=6)
        self.app.aplicar_paleta()
        self._rotulo_previa()
        self.recarregar()
        if r.pedir_nova_imagem:
            self._pedir_nova_imagem(t)

    def _pedir_nova_imagem(self, t: Tema) -> None:
        def depois(escolha: str | None) -> None:
            if not escolha:
                return
            if escolha == SEM_PADRAO:
                self.app.temas.definir_fundo_padrao(t, None)
                self.recarregar()
                return
            try:
                imagem = self.app.temas.definir_fundo_padrao(t, Path(escolha))
            except (ValueError, OSError) as exc:
                self.app.push_screen(Aviso("Imagem recusada", str(exc)))
                return
            r = self.app.omarchy.theme_bg_set(imagem)
            self.app.notify(f"Fundo {imagem.name} aplicado." if r.ok else f"Falha no fundo: {r.erro_legivel}", severity="information" if r.ok else "error")
            self.recarregar()

        tema_novo = next((x for x in self.temas if x.slug == t.slug), t)
        self.app.push_screen(EscolherFundo(tema_novo, "A imagem padrão sumiu. Escolha outra"), depois)

    # Busca e navegação

    def action_buscar(self) -> None:
        self.query_one("#temas-busca", Input).focus()

    def action_limpar_busca(self) -> None:
        if self._previa_ligada or self.app.previa.ativa:
            self.encerrar_previa()
        busca = self.query_one("#temas-busca", Input)
        if busca.value:
            busca.value = ""
        self.query_one("#temas-tabela", DataTable).focus()

    @on(Input.Changed, "#temas-busca")
    def _busca_mudou(self, ev: Input.Changed) -> None:
        self._filtro = ev.value.strip()
        self._renderizar()

    @on(Input.Submitted, "#temas-busca")
    def _busca_enter(self) -> None:
        self.query_one("#temas-tabela", DataTable).focus()

    def action_cursor_baixo(self) -> None:
        self.query_one("#temas-tabela", DataTable).action_cursor_down()

    def action_cursor_cima(self) -> None:
        self.query_one("#temas-tabela", DataTable).action_cursor_up()
