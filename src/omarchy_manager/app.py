"""Aplicação Textual: três abas, ajuda, barra inferior e paleta do tema ativo."""

from __future__ import annotations

import argparse
import sys
import time

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Button, Header, TabbedContent, TabPane

from omarchy_manager import __version__
from omarchy_manager.services import abertura as abertura_svc
from omarchy_manager.services import caminhos, terminal_foot, terminal_grafico
from omarchy_manager.services import webapps as webapps_servico
from omarchy_manager.services.ai_launcher import AiLauncher
from omarchy_manager.services.hyprland import HyprlandService
from omarchy_manager.services.log import configurar_log, logger
from omarchy_manager.services.omarchy import OmarchyService
from omarchy_manager.services.overrides import GerenciadorOverrides
from omarchy_manager.services.shortcut_capture import CapturaHyprland
from omarchy_manager.services.paleta import paleta_atual, tema_textual
from omarchy_manager.services.plugin_catalog import PluginCatalog
from omarchy_manager.services.temas import ThemeService
from omarchy_manager.services.previa_ao_vivo import PreviaAoVivo
from omarchy_manager.ui.abertura import Abertura
from omarchy_manager.ui.compartilhar import AbaCompartilhar
from omarchy_manager.ui.navegacao import AjudaAba, RodapeEnxuto
from omarchy_manager.ui.config import AbaConfig
from omarchy_manager.ui.dialogs import Ajuda
from omarchy_manager.ui.fundo import AbaFundo
from omarchy_manager.ui.imagem import ImagemTerminal
from omarchy_manager.ui.plugins import AbaPlugins
from omarchy_manager.ui.shortcuts import AbaAtalhos
from omarchy_manager.ui.terminal import AbaTerminal
from omarchy_manager.ui.webapps import AbaWebapps
from omarchy_manager.ui.themes import AbaTemas


class OmarchyManagerApp(App[None]):
    TITLE = "Omarchy Manager"
    CSS = """
    Screen { background: $background; color: $foreground; }
    TabbedContent { height: 1fr; }
    TabPane { padding: 0 1; }
    DataTable { height: 1fr; }
    .aviso { color: $warning; }
    .erro { color: $error; }
    .ok { color: $success; }
    .mudo { color: $text-muted; }
    """
    BINDINGS = [
        Binding("q", "quit", "Sair"),
        Binding("question_mark", "ajuda", "Ajuda", key_display="?"),
        Binding("1", "aba('atalhos')", "Atalhos", show=False),
        Binding("2", "aba('plugins')", "Plugins", show=False),
        Binding("3", "aba('temas')", "Temas", show=False),
        Binding("4", "aba('config')", "Config", show=False),
        Binding("5", "aba('fundo')", "Fundo", show=False),
        Binding("6", "aba('terminal')", "Terminal", show=False),
        Binding("7", "aba('compartilhar')", "Compartilhar", show=False),
        Binding("8", "aba('webapps')", "Webapps", show=False),
        Binding("alt+l,alt+right", "aba_relativa(1)", "Próxima aba", key_display="Alt+L", priority=True),
        Binding("alt+h,alt+left", "aba_relativa(-1)", "Aba anterior", key_display="Alt+H", priority=True),
        Binding("ctrl+right,ctrl+l", "botao(1)", "Próximo botão", key_display="Ctrl+→", priority=True),
        Binding("ctrl+left,ctrl+h", "botao(-1)", "Botão anterior", key_display="Ctrl+←", priority=True),
        Binding("ctrl+down,ctrl+j", "secao(1)", "Próxima seção", key_display="Ctrl+↓", priority=True),
        Binding("ctrl+up,ctrl+k", "secao(-1)", "Seção anterior", key_display="Ctrl+↑", priority=True),
        Binding("ctrl+@,ctrl+space,ctrl+at,f1", "ajuda_aba", "Ajuda", key_display="Ctrl+Espaço", priority=True),
        Binding("ctrl+enter", "botao_acionar", "Apertar botão", key_display="Ctrl+Enter", priority=True),
        Binding("escape", "voltar_foco", "Voltar à lista", show=False),
        Binding("f5", "recarregar", "Recarregar"),
        Binding("slash", "buscar", "Pesquisar", key_display="/"),
    ]

    def __init__(
        self,
        omarchy: OmarchyService | None = None,
        hyprland: HyprlandService | None = None,
        catalogo: PluginCatalog | None = None,
        temas: ThemeService | None = None,
        overrides: GerenciadorOverrides | None = None,
        captura: CapturaHyprland | None = None,
        ia: AiLauncher | None = None,
        previa: PreviaAoVivo | None = None,
        aba_inicial: str = "plugins",
    ) -> None:
        super().__init__()
        self.omarchy = omarchy or OmarchyService()
        self.hyprland = hyprland or HyprlandService()
        self.catalogo = catalogo or PluginCatalog()
        self.temas = temas or ThemeService(self.omarchy)
        self.overrides = overrides or GerenciadorOverrides(self.hyprland)
        self.captura = captura or CapturaHyprland(self.hyprland)
        self.ia = ia or AiLauncher()
        self.previa = previa or PreviaAoVivo(self.omarchy)
        self.webapps_ativa = webapps_servico.aba_ativa()
        self._aba_alvo = ""
        self._aba_alvo_em = 0.0
        self.aba_inicial = aba_inicial if aba_inicial in self.ORDEM_ABAS[:-1] or (aba_inicial == "webapps" and self.webapps_ativa) else "plugins"
        self.deteccao = self.omarchy.detectar()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with TabbedContent(initial=self.aba_inicial, id="abas"):
            with TabPane("Atalhos", id="atalhos"):
                yield AbaAtalhos()
            with TabPane("Plugins", id="plugins"):
                yield AbaPlugins()
            with TabPane("Temas", id="temas"):
                yield AbaTemas()
            with TabPane("Config", id="config"):
                yield AbaConfig()
            with TabPane("Fundo", id="fundo"):
                yield AbaFundo()
            with TabPane("Terminal", id="terminal"):
                yield AbaTerminal()
            with TabPane("Compartilhar", id="compartilhar"):
                yield AbaCompartilhar()
            with TabPane("Webapps", id="webapps"):
                yield AbaWebapps()
        yield RodapeEnxuto()

    def on_mount(self) -> None:
        self.aplicar_paleta()
        if not self.webapps_ativa:
            self.query_one("#abas", TabbedContent).hide_tab("webapps")
        self.sub_title = self.deteccao.mensagem
        if abertura_svc.deve_mostrar():
            abertura_svc.marcar()
            self.push_screen(Abertura(f"v{__version__}"), lambda _: self.call_after_refresh(self.focar_tabela))
        else:
            self.call_after_refresh(self.focar_tabela)
        if not self.deteccao.omarchy:
            self.notify(self.deteccao.mensagem, severity="warning", timeout=8)

    def aplicar_paleta(self) -> None:
        """Relê o colors.toml do tema ativo e troca o tema do Textual."""
        paleta = paleta_atual()
        nome = "omarchy-claro" if not paleta.escuro else "omarchy-escuro"
        self.register_theme(tema_textual(paleta, nome))
        if self.theme == nome:
            self.refresh_css()  # mesmo nome, cores novas: o Textual não refaz o CSS sozinho
        self.theme = nome
        self.reafirmar_transparencia(paleta)
        if paleta.ausentes:
            logger.info("paleta sem as chaves %s, usando ANSI", ", ".join(paleta.ausentes))

    def reafirmar_transparencia(self, paleta=None) -> None:
        """Devolve ao Foot o alpha do usuário, que o `omarchy theme set` troca por opaco."""
        paleta = paleta or paleta_atual()
        seq = terminal_foot.sequencia_alpha(paleta.background, paleta.escuro)
        if not seq:
            return
        try:
            if self._driver is not None:
                self._driver.write(seq)
                self._driver.flush()
        except Exception:
            pass

    def push_screen(self, *args, **kwargs):
        # Imagem do protocolo kitty não é apagada por texto escrito por cima: tira antes do diálogo.
        if self.is_mounted:
            for foto in self.query(ImagemTerminal):
                foto.apagar()
        return super().push_screen(*args, **kwargs)

    def nav_da_aba(self):
        """A aba ativa (ou o diálogo aberto, se tiver navegação própria)."""
        if len(self.screen_stack) > 1:
            return self.screen if hasattr(self.screen, "mover_secao") else None
        tipo = self.aba_ativa()
        return self.query_one(tipo) if tipo is not None and hasattr(tipo, "mover_secao") else None

    def check_action(self, action: str, parameters: tuple[object, ...]):
        # Ctrl+j/k e a ajuda da aba valem em toda aba; em diálogo, só a troca de zona.
        if action == "ajuda_aba":
            return len(self.screen_stack) == 1 and self.nav_da_aba() is not None
        if action == "secao":
            return self.nav_da_aba() is not None
        return True

    def action_secao(self, passo: int) -> None:
        nav = self.nav_da_aba()
        if nav is not None:
            nav.mover_secao(passo)

    def action_ajuda_aba(self) -> None:
        nav = self.nav_da_aba()
        if nav is not None:
            self.push_screen(AjudaAba(nav.TITULO_AJUDA or "esta aba", nav.texto_ajuda()))

    def action_voltar_foco(self) -> None:
        nav = self.nav_da_aba()
        if nav is not None and len(self.screen_stack) == 1:
            nav.focar_entrada()

    def action_ajuda(self) -> None:
        self.push_screen(Ajuda())

    def aba_ativa(self):
        abas = self.query_one("#abas", TabbedContent)
        return {"atalhos": AbaAtalhos, "plugins": AbaPlugins, "temas": AbaTemas, "config": AbaConfig, "fundo": AbaFundo, "terminal": AbaTerminal, "compartilhar": AbaCompartilhar, "webapps": AbaWebapps}.get(abas.active)

    ORDEM_ABAS = ("atalhos", "plugins", "temas", "config", "fundo", "terminal", "compartilhar", "webapps")

    def abas_visiveis(self) -> tuple[str, ...]:
        """Webapps é a última aba (tecla 8): oculta, não renumera nenhuma das outras."""
        return self.ORDEM_ABAS if self.webapps_ativa else self.ORDEM_ABAS[:-1]

    def aplicar_aba_webapps(self, ativa: bool) -> None:
        """Mostra ou esconde a aba Webapps. Escondida com ela aberta, volta para a Config."""
        self.webapps_ativa = ativa
        abas = self.query_one("#abas", TabbedContent)
        if ativa:
            abas.show_tab("webapps")
        else:
            if abas.active == "webapps":
                self._ir_para_aba("config")
            abas.hide_tab("webapps")

    def action_aba(self, aba: str) -> None:
        if len(self.screen_stack) > 1:  # diálogo aberto: não troca por baixo dele
            return
        if aba not in self.abas_visiveis():
            return
        self._ir_para_aba(aba)

    def _ir_para_aba(self, aba: str) -> None:
        # O TabbedContent confirma a troca por mensagem. Com duas trocas seguidas, a
        # confirmação atrasada da primeira desfazia a segunda. Guardamos o destino.
        self._aba_alvo = aba
        self._aba_alvo_em = time.monotonic()
        self.query_one("#abas", TabbedContent).active = aba
        self.call_after_refresh(self.focar_tabela)

    def action_aba_relativa(self, passo: int) -> None:
        if len(self.screen_stack) > 1:
            return
        abas = self.query_one("#abas", TabbedContent)
        base = self._aba_alvo or abas.active
        ordem = self.abas_visiveis()
        atual = ordem.index(base) if base in ordem else 0
        self._ir_para_aba(ordem[(atual + passo) % len(ordem)])

    def _botoes(self) -> list[Button]:
        """Botões visíveis e ativos da tela atual (do diálogo, se houver; senão da aba ativa)."""
        if len(self.screen_stack) > 1:
            raiz = self.screen
        else:
            tipo = self.aba_ativa()
            if tipo is None:
                return []
            raiz = self.query_one(tipo)
        nav = self.nav_da_aba()
        fileira = nav.fileira() if nav is not None else []
        if fileira:
            return [w for w in fileira if w.focusable]
        return [b for b in raiz.query(Button) if b.display and not b.disabled and b.region.area > 0]

    def action_botao(self, passo: int) -> None:
        botoes = self._botoes()
        if not botoes:
            return
        atual = self.focused
        if atual in botoes:
            botoes[(botoes.index(atual) + passo) % len(botoes)].focus()
        else:
            botoes[0 if passo > 0 else -1].focus()

    def action_botao_acionar(self) -> None:
        if isinstance(self.focused, Button) and not self.focused.disabled:
            self.focused.press()

    def focar_tabela(self) -> None:
        tipo = self.aba_ativa()
        if tipo is None:
            return
        self.query_one(tipo).focar_entrada()

    def action_buscar(self) -> None:
        tipo = self.aba_ativa()
        if tipo is not None:
            self.query_one(tipo).action_buscar()

    @on(TabbedContent.TabActivated)
    def _aba_mudou(self) -> None:
        abas = self.query_one("#abas", TabbedContent)
        if abas.active != "temas":
            self.query_one(AbaTemas).gravar_padrao_pendente()
        if self._aba_alvo and abas.active != self._aba_alvo and time.monotonic() - self._aba_alvo_em < 0.6:
            abas.active = self._aba_alvo  # confirmação atrasada de uma troca anterior
            return
        self._aba_alvo = abas.active  # troca vinda do mouse ou das setas na barra de abas
        if self.query_one("#abas", TabbedContent).active != "temas":
            self.query_one(AbaTemas).encerrar_previa()
            for foto in self.query(ImagemTerminal):
                foto.apagar()
        self.call_after_refresh(self.focar_tabela)

    async def action_quit(self) -> None:
        for aba in self.query(AbaCompartilhar):
            aba.parar_oferta()
        for aba in self.query(AbaTemas):
            aba.gravar_padrao_pendente()
        if self.previa.restaurar():
            self.reafirmar_transparencia()
        self.exit()

    def action_recarregar(self) -> None:
        self.aplicar_paleta()
        aba = self.query_one("#abas", TabbedContent).active
        for widget in self.query("AbaAtalhos, AbaPlugins, AbaTemas, AbaFundo, AbaTerminal, AbaCompartilhar, AbaWebapps"):
            recarregar = getattr(widget, "recarregar", None)
            if recarregar is not None:
                recarregar()
        self.notify(f"Aba {aba} recarregada", timeout=3)

    def ir_para_atalhos_do_plugin(self, plugin_id: str) -> None:
        self.action_aba("atalhos")
        self.query_one(AbaAtalhos).filtrar_por_plugin(plugin_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="omarchy-manager", description="Gerenciador TUI do Omarchy")
    parser.add_argument("--versao", action="version", version=f"omarchy-manager {__version__}")
    parser.add_argument("--aba", choices=OmarchyManagerApp.ORDEM_ABAS, default="plugins", help="aba aberta ao iniciar")
    sub = parser.add_subparsers(dest="comando")
    p_share = sub.add_parser("share", help="compartilhar um plugin de terceiros ou tema do usuário na rede local")
    p_share.add_argument("id", help="id do plugin ou slug do tema")
    p_receive = sub.add_parser("receive", help="receber um pacote de outro computador na rede local")
    p_receive.add_argument("--convite", help="texto omarchy-manager://host:porta/fingerprint/segredo")
    p_receive.add_argument("--instalar", action="store_true", help="oferecer instalação após revisar (plugin fica desligado)")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    caminhos.preparar_diretorios()
    configurar_log()
    if args.comando == "share":
        from omarchy_manager.cli_share import share

        return share(args.id)
    if args.comando == "receive":
        from omarchy_manager.cli_share import receive

        return receive(args.convite, args.instalar)
    previa = PreviaAoVivo(OmarchyService())
    if previa.pendente():
        print("Uma prévia de tema ficou aplicada na última sessão; restaurando o tema anterior…")
        previa.restaurar()
    terminal_grafico.sondar()  # antes de o Textual assumir a entrada
    app = OmarchyManagerApp(previa=previa, aba_inicial=args.aba)
    previa.instalar_rede_de_seguranca()
    try:
        app.run()
    finally:
        if previa.restaurar():
            # a restauração também passa pelo `omarchy theme set`, que deixa o Foot opaco
            paleta = paleta_atual()
            sys.__stdout__.write(terminal_foot.sequencia_alpha(paleta.background, paleta.escuro))
            sys.__stdout__.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
