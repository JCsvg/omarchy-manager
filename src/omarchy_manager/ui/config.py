"""Aba Config: os atalhos de teclado do próprio omarchy-manager e os caminhos
de configuração e estado. Somente leitura. A tabela é montada a partir dos
BINDINGS reais de cada tela, então não fica desatualizada."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import DataTable, Static

from omarchy_manager.services import caminhos

NOMES_TECLA = {
    "question_mark": "?", "slash": "/", "space": "Espaço", "escape": "Esc", "enter": "Enter",
    "left": "←", "right": "→", "up": "↑", "down": "↓",
}

FIXOS = [
    ("Global", "Tab / Shift+Tab", "Mudar o foco entre campos e botões"),
    ("Global", "↑ / ↓", "Navegar na lista"),
    ("Global", "Enter", "Executar a ação em foco"),
    ("Global", "Clique do mouse", "Selecionar, ativar um botão ou trocar de aba"),
    ("Plugins", "Mouse sobre o nome", "Mostrar a descrição do plugin"),
    ("Temas", "Segurar Ctrl", "Prévia ao vivo do tema em foco ou sob o mouse; soltar volta ao anterior"),
    ("Atalhos (captura)", "Qualquer combinação", "Vira a nova combinação do atalho em edição"),
    ("Diálogos", "Esc", "Cancelar e fechar"),
]


def tecla_legivel(tecla: str) -> str:
    partes = []
    for p in tecla.split("+"):
        if p in NOMES_TECLA:
            partes.append(NOMES_TECLA[p])
        elif p in ("ctrl", "alt", "shift", "super"):
            partes.append(p.capitalize())
        else:
            partes.append(p.upper() if len(p) == 1 or (p.startswith("f") and p[1:].isdigit()) else p)
    return "+".join(partes)


def linhas_de_bindings(contexto: str, bindings) -> list[tuple[str, str, str]]:
    linhas = []
    for b in bindings:
        if not isinstance(b, Binding) or not b.description:
            continue
        teclas = " / ".join(tecla_legivel(k.strip()) for k in b.key.split(","))
        linhas.append((contexto, teclas, b.description))
    return linhas


def todos_os_atalhos() -> list[tuple[str, str, str]]:
    from omarchy_manager.app import OmarchyManagerApp
    from omarchy_manager.ui.plugins import AbaPlugins
    from omarchy_manager.ui.shortcuts import AbaAtalhos
    from omarchy_manager.ui.themes import AbaTemas

    linhas = linhas_de_bindings("Global", OmarchyManagerApp.BINDINGS)
    linhas += [f for f in FIXOS if f[0] == "Global"]
    for contexto, classe in (("Atalhos", AbaAtalhos), ("Plugins", AbaPlugins), ("Temas", AbaTemas)):
        linhas += linhas_de_bindings(contexto, classe.BINDINGS)
        linhas += [f for f in FIXOS if f[0].startswith(contexto)]
    linhas += [f for f in FIXOS if f[0] == "Diálogos"]
    return linhas


def caminhos_legiveis() -> str:
    itens = [
        ("Imagem padrão por tema", caminhos.CONFIG_TOML),
        ("Aliases plugin e atalho", caminhos.PLUGIN_SHORTCUTS_TOML),
        ("Traduções de plugins (suas)", caminhos.CONFIG_DIR / "plugins-pt-BR.json"),
        ("Atalhos gerenciados (gerado)", caminhos.HYPR_MANAGER_BINDINGS),
        ("Backups", caminhos.BACKUPS_DIR),
        ("Log", caminhos.LOG_FILE),
        ("Estado da prévia ao vivo", caminhos.STATE_DIR / "previa-original.json"),
        ("Workspaces da IA", caminhos.THEME_WORKSPACES_DIR),
        ("Pacotes recebidos", caminhos.DATA_DIR / "recebidos"),
    ]
    largura = max(len(r) for r, _ in itens)
    return "\n".join(f"{r:<{largura}}  {c}" for r, c in itens)


class AbaConfig(Vertical):
    DEFAULT_CSS = """
    AbaConfig { height: 1fr; }
    #config-titulo { color: $accent; text-style: bold; height: 1; }
    #config-tabela { height: 1fr; }
    #config-caminhos-titulo { color: $accent; text-style: bold; height: 1; margin-top: 1; }
    #config-caminhos { height: auto; color: $text-muted; }
    """
    BINDINGS = [
        Binding("j", "cursor_baixo", "Descer na lista", show=False),
        Binding("k", "cursor_cima", "Subir na lista", show=False),
    ]

    def compose(self) -> ComposeResult:
        yield Static("Atalhos de teclado do omarchy-manager (somente leitura)", id="config-titulo")
        tabela = DataTable(id="config-tabela", cursor_type="row", zebra_stripes=True)
        tabela.add_columns("Onde", "Tecla", "O que faz")
        yield tabela
        yield Static("Arquivos de configuração e estado", id="config-caminhos-titulo")
        yield Static(caminhos_legiveis(), id="config-caminhos")

    def on_mount(self) -> None:
        tabela = self.query_one("#config-tabela", DataTable)
        for linha in todos_os_atalhos():
            tabela.add_row(*linha)

    def recarregar(self) -> None:
        pass

    def action_buscar(self) -> None:
        pass

    def action_cursor_baixo(self) -> None:
        self.query_one("#config-tabela", DataTable).action_cursor_down()

    def action_cursor_cima(self) -> None:
        self.query_one("#config-tabela", DataTable).action_cursor_up()
