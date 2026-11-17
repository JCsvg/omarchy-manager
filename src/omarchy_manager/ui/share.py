"""Diálogos de Compartilhar e Receber (plano, seção 10)."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static

from omarchy_manager.services import caminhos
from omarchy_manager.services.bundle import (
    ErroBundle,
    aviso_licenca,
    criar_bundle,
    executaveis_em,
    extrair_para_temporario,
    instalar_recebido,
    listar_arquivos,
)
from omarchy_manager.services.lan_share import ErroLan, ServidorEnvio, baixar, codigo_de_confirmacao, descobrir, interpretar_convite
from omarchy_manager.services.qr import qr_markup
from omarchy_manager.ui.dialogs import CSS_DIALOGO, DICA_FORMULARIO, Aviso, Dialogo

RECEBIDOS_DIR = caminhos.DATA_DIR / "recebidos"
EXPORT_DIR = Path.home() / "Downloads"


def resumo_do_bundle(man, pasta: Path) -> str:
    """Texto de revisão de um plugin ou tema recebido (manifesto, hash, executáveis)."""
    exe = executaveis_em(pasta)
    return (
        f"[b]{man.nome}[/b] ({man.tipo} {man.id}) v{man.versao or '?'} de {man.autor or '?'}\n"
        f"licença: {man.licenca or '(ausente)'}   origem: {man.origem or '?'}\n"
        f"{len(man.arquivos)} arquivos, {man.tamanho / 1024:.0f} KiB, hash conferido\n"
        f"executáveis/código: {', '.join(exe) if exe else 'nenhum'}\n"
        + ("[yellow]Plugins rodam sem sandbox. Será instalado DESLIGADO.[/yellow]" if man.tipo == "plugin" else "O tema NÃO será aplicado; aparece na aba Temas para prévia.")
    )


def instalar_revisado(tela, pasta: Path, man) -> None:
    """Instala o recebido já revisado. Se já existe, pergunta antes de substituir (com backup).
    Fecha `tela` devolvendo o destino. Nunca liga o plugin nem aplica o tema."""
    try:
        r = instalar_recebido(pasta, man, confirmado=True)
    except ErroBundle as exc:
        if "já existe" in str(exc):
            from omarchy_manager.ui.dialogs import Confirmacao

            def depois(ok: bool | None) -> None:
                if ok:
                    r2 = instalar_recebido(pasta, man, confirmado=True, substituir=True)
                    tela.app.notify(r2.aviso, severity="warning", timeout=8)
                    tela.dismiss(r2.destino)

            tela.app.push_screen(Confirmacao("Já existe", f"{exc}\n\nSubstituir após backup?", confirmar="Substituir após backup", perigo=True), depois)
            return
        tela.app.push_screen(Aviso("Falha ao instalar", str(exc)))
        return
    tela.app.notify(r.aviso, severity="warning", timeout=8)
    tela.dismiss(r.destino)


class Compartilhar(Dialogo):
    FOCO_INICIAL = "#cancelar"

    """Revisão (licença, arquivos, tamanho) -> enviar na LAN ou guardar como arquivo."""

    DEFAULT_CSS = CSS_DIALOGO + """
    Compartilhar #caixa { width: 100; max-height: 98%; overflow-y: auto; }
    Compartilhar #codigo { text-style: bold; color: $accent; border: round $panel; padding: 0 1; height: auto; }
    """
    BINDINGS = [Binding("escape", "cancelar", "Cancelar", priority=True)]

    def __init__(self, tipo: str, ident: str, nome: str, pasta: Path, *, versao: str = "", autor: str = "",
                 licenca: str = "", origem: str = "") -> None:
        super().__init__()
        self.tipo, self.ident, self.nome, self.pasta = tipo, ident, nome, pasta
        self.meta = dict(versao=versao, autor=autor, licenca=licenca, origem=origem)
        self._servidor: ServidorEnvio | None = None
        self._tmp: Path | None = None

    def compose(self) -> ComposeResult:
        arquivos = listar_arquivos(self.pasta)
        tamanho = sum(a.stat().st_size for a in arquivos)
        aviso = aviso_licenca(self.meta["licenca"])
        with Vertical(id="caixa"):
            yield Label(f"Compartilhar {self.tipo}: {self.nome}", classes="titulo")
            yield Static(
                f"licença: {self.meta['licenca'] or '(ausente)'}\n"
                f"{len(arquivos)} arquivos, {tamanho / 1024:.0f} KiB (sem .git, credenciais, caches, logs e backups)\n"
                + (f"[yellow]{aviso}[/yellow]" if aviso else "")
            )
            yield Static("", id="codigo")
            yield Static("", id="share-status", classes="mudo")
            with Horizontal(id="botoes"):
                yield Button("Cancelar", id="cancelar")
                yield Button("Guardar como arquivo", id="exportar")
                yield Button("Enviar na rede local", id="enviar", variant="primary")

    def _bundle(self) -> tuple[Path, str]:
        self._tmp = Path(tempfile.mkdtemp(prefix="omarchy-manager-bundle-"))
        arq, _, sha = criar_bundle(self.tipo, self.ident, self.nome, self.pasta, self._tmp, **self.meta)
        return arq, sha

    @on(Button.Pressed, "#exportar")
    def _exportar(self) -> None:
        try:
            arq, sha = self._bundle()
            EXPORT_DIR.mkdir(parents=True, exist_ok=True)
            destino = caminhos.garantir_gravavel(EXPORT_DIR / arq.name)
            destino.write_bytes(arq.read_bytes())
        except (ErroBundle, OSError, caminhos.CaminhoProibido) as exc:
            self.query_one("#share-status", Static).update(f"[red]{exc}[/red]")
            return
        self.query_one("#codigo", Static).update(f"Arquivo guardado em:\n{destino}\nSHA-256: {sha}\nEnvie o hash por outro canal para o destinatário conferir.")
        self.query_one("#enviar", Button).disabled = True

    @on(Button.Pressed, "#enviar")
    def _enviar(self) -> None:
        self.query_one("#enviar", Button).disabled = True
        self.query_one("#exportar", Button).disabled = True
        self.query_one("#share-status", Static).update("Preparando pacote e certificado…")
        self._servir()

    @work(thread=True, exclusive=True, group="share")
    def _servir(self) -> None:
        try:
            arq, sha = self._bundle()
            self._servidor = ServidorEnvio(arq, sha)
            s = self._servidor.iniciar()
        except (ErroBundle, ErroLan, OSError) as exc:
            self.app.call_from_thread(self.query_one("#share-status", Static).update, f"[red]{exc}[/red]")
            return
        texto = (
            f"Computador: {s.host}   porta: {s.porta}\n"
            f"Código de confirmação (confira igual no outro lado):\n  [b]{s.codigo}[/b]\n"
            f"Fingerprint: {s.fingerprint[:16]}…\n"
            f"Convite (cole em Receber ou leia o QR):\n{s.convite}\n"
            "Válido por 10 minutos ou 1 download."
        )
        qr = qr_markup(s.convite)
        if qr:
            texto += "\n" + qr
        self.app.call_from_thread(self.query_one("#codigo", Static).update, texto)
        self.app.call_from_thread(self.query_one("#share-status", Static).update, "Aguardando o outro computador…")
        baixou = self._servidor.esperar()
        self.app.call_from_thread(self._fim, baixou)

    def _fim(self, baixou: bool) -> None:
        self.query_one("#share-status", Static).update("Enviado. Pode fechar." if baixou else "Encerrado sem envio (cancelado ou expirou).")
        self._encerrar()

    def _encerrar(self) -> None:
        if self._servidor:
            self._servidor.encerrar()
            self._servidor = None
        if self._tmp:
            import shutil

            shutil.rmtree(self._tmp, ignore_errors=True)
            self._tmp = None

    def on_button_pressed(self, ev: Button.Pressed) -> None:
        if ev.button.id == "cancelar":
            self.action_cancelar()

    def action_cancelar(self) -> None:
        self._encerrar()
        self.dismiss(None)


class Receber(Dialogo):
    DICA = DICA_FORMULARIO

    """Cole o convite (ou escolha um par descoberto), confira o código, baixe, revise e instale desligado."""

    DEFAULT_CSS = CSS_DIALOGO + """
    Receber #caixa { width: 90; }
    Receber #resumo { height: auto; max-height: 18; border: round $panel; padding: 0 1; }
    """
    BINDINGS = [Binding("escape", "cancelar", "Cancelar", priority=True)]

    def __init__(self) -> None:
        super().__init__()
        self._pasta: Path | None = None
        self._manifesto = None

    def compose(self) -> ComposeResult:
        with Vertical(id="caixa"):
            yield Label("Receber plugin ou tema da rede local", classes="titulo")
            yield Static("Cole o convite mostrado no outro computador (omarchy-manager://…). Os 2 lados devem mostrar o mesmo código antes de confirmar.")
            yield Input(placeholder="omarchy-manager://host:porta/fingerprint/segredo", id="convite")
            yield Static("", id="pares", classes="mudo")
            with VerticalScroll(id="resumo"):
                yield Static("", id="resumo-texto")
            yield Static("", id="rec-status", classes="mudo")
            with Horizontal(id="botoes"):
                yield Button("Cancelar", id="cancelar")
                yield Button("Procurar na rede", id="procurar")
                yield Button("Conferir código", id="conferir", variant="primary")
                yield Button("Baixar", id="baixar", disabled=True)
                yield Button("Instalar desligado", id="instalar", disabled=True)

    def on_mount(self) -> None:
        super().on_mount()
        self.query_one("#convite", Input).focus()

    @on(Button.Pressed, "#procurar")
    def _procurar(self) -> None:
        self.query_one("#rec-status", Static).update("Procurando anúncios _omarchy-manager._tcp…")
        self._descobrir()

    @work(thread=True, group="receber")
    def _descobrir(self) -> None:
        pares = descobrir()
        texto = "\n".join(f"{p.nome}: {p.endereco}:{p.porta} fp {p.fingerprint[:16]}…" for p in pares) or "Nenhum computador anunciando agora (ou avahi ausente)."
        self.app.call_from_thread(self.query_one("#pares", Static).update, texto)
        self.app.call_from_thread(self.query_one("#rec-status", Static).update, "")

    @on(Button.Pressed, "#conferir")
    def _conferir(self) -> None:
        try:
            host, porta, fp, segredo = interpretar_convite(self.query_one("#convite", Input).value)
        except ErroLan as exc:
            self.query_one("#rec-status", Static).update(f"[red]{exc}[/red]")
            return
        self.query_one("#resumo-texto", Static).update(
            f"Computador: {host}:{porta}\nCódigo de confirmação:\n  [b]{codigo_de_confirmacao(fp, segredo)}[/b]\n"
            "Se for igual ao do outro lado, clique em Baixar."
        )
        self.query_one("#baixar", Button).disabled = False

    @on(Button.Pressed, "#baixar")
    def _baixar(self) -> None:
        self.query_one("#baixar", Button).disabled = True
        self.query_one("#rec-status", Static).update("Baixando…")
        self._download(self.query_one("#convite", Input).value)

    @work(thread=True, exclusive=True, group="receber")
    def _download(self, convite: str) -> None:
        try:
            host, porta, fp, segredo = interpretar_convite(convite)
            RECEBIDOS_DIR.mkdir(parents=True, exist_ok=True)
            arq, sha = baixar(host, porta, fp, segredo, RECEBIDOS_DIR / f"recebido-{porta}.omarchy-bundle")
            pasta, man = extrair_para_temporario(arq, sha or None)
        except (ErroLan, ErroBundle, OSError) as exc:
            self.app.call_from_thread(self.query_one("#rec-status", Static).update, f"[red]Recusado: {exc}[/red]")
            return
        self._pasta, self._manifesto = pasta, man
        resumo = resumo_do_bundle(man, pasta)
        self.app.call_from_thread(self.query_one("#resumo-texto", Static).update, resumo)
        self.app.call_from_thread(self.query_one("#rec-status", Static).update, "Revise e, se concordar, instale.")
        self.app.call_from_thread(setattr, self.query_one("#instalar", Button), "disabled", False)

    @on(Button.Pressed, "#instalar")
    def _instalar(self) -> None:
        if self._pasta is None or self._manifesto is None:
            return
        instalar_revisado(self, self._pasta, self._manifesto)

    def on_button_pressed(self, ev: Button.Pressed) -> None:
        if ev.button.id == "cancelar":
            self.action_cancelar()

    def action_cancelar(self) -> None:
        self.dismiss(None)


class RevisarBundle(Dialogo):
    """Revisão de um plugin ou tema já baixado e validado (vindo da aba Compartilhar). Mesmo fluxo do Receber."""

    DEFAULT_CSS = CSS_DIALOGO + """
    RevisarBundle #caixa { width: 90; }
    RevisarBundle #resumo { height: auto; max-height: 18; border: round $panel; padding: 0 1; }
    """
    BINDINGS = [Binding("escape", "cancelar", "Cancelar", priority=True)]
    FOCO_INICIAL = "#cancelar"

    def __init__(self, pasta: Path, manifesto, origem: str = "") -> None:
        super().__init__()
        self._pasta, self._manifesto, self._origem = pasta, manifesto, origem

    def compose(self) -> ComposeResult:
        with Vertical(id="caixa"):
            yield Label(f"Revisar {self._manifesto.tipo} recebido" + (f" de {self._origem}" if self._origem else ""), classes="titulo")
            with VerticalScroll(id="resumo"):
                yield Static(resumo_do_bundle(self._manifesto, self._pasta))
            with Horizontal(id="botoes"):
                yield Button("Cancelar", id="cancelar")
                yield Button("Instalar desligado", id="instalar", variant="primary")

    @on(Button.Pressed, "#instalar")
    def _instalar(self) -> None:
        instalar_revisado(self, self._pasta, self._manifesto)

    @on(Button.Pressed, "#cancelar")
    def action_cancelar(self) -> None:
        shutil.rmtree(self._pasta, ignore_errors=True)
        self.dismiss(None)
