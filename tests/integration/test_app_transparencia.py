"""Recarregar a paleta depois de uma troca de tema: o fundo da tela continua sendo a cor
de fundo do tema (a mesma que o terminal usa como padrão) e o alpha do Foot é reafirmado."""

import pytest
from textual.widgets import DataTable

from omarchy_manager.app import OmarchyManagerApp
from omarchy_manager.services import caminhos, terminal_foot, terminal_grafico
from omarchy_manager.services.hyprland import HyprlandService
from omarchy_manager.services.omarchy import OmarchyService
from omarchy_manager.services.plugin_catalog import PluginCatalog
from omarchy_manager.services.previa_ao_vivo import PreviaAoVivo
from omarchy_manager.services.temas import ThemeService
from omarchy_manager.services.terminal_grafico import Capacidades
from omarchy_manager.ui.dialogs import Confirmacao

ESCURO_A = 'mode = "dark"\nbackground = "#1a1b26"\nforeground = "#a9b1d6"\naccent = "#9ece6a"\nmuted = "#414868"\nred = "#f7768e"\ngreen = "#9ece6a"\nyellow = "#e0af68"\nblue = "#7aa2f7"\nselection = "#2f3b25"\n'
ESCURO_B = ESCURO_A.replace("#1a1b26", "#0c0b0c").replace("#9ece6a", "#b59790")
CLARO = ESCURO_A.replace('"dark"', '"light"').replace("#1a1b26", "#eff1f5").replace("#a9b1d6", "#4c4f69")


@pytest.fixture
def app(tmp_path, executor, monkeypatch):
    monkeypatch.setattr(caminhos, "PROIBIDOS", (tmp_path / "proibido",))
    monkeypatch.delenv("HYPRLAND_INSTANCE_SIGNATURE", raising=False)
    estado = tmp_path / "estado"
    (estado / "theme").mkdir(parents=True)
    (estado / "theme" / "colors.toml").write_text(ESCURO_A)
    (estado / "theme.name").write_text("a\n")
    monkeypatch.setattr(caminhos, "OMARCHY_STATE_CURRENT", estado)
    sistema = tmp_path / "sistema"
    for slug, cores in (("a", ESCURO_A), ("b", ESCURO_B)):
        (sistema / slug).mkdir(parents=True)
        (sistema / slug / "colors.toml").write_text(cores)
    foot_ini = tmp_path / "foot.ini"
    foot_ini.write_text("[colors-dark]\nalpha=0.25\nalpha-mode=all\n[colors-light]\nalpha=0.25\n")
    monkeypatch.setattr(terminal_foot, "_config_do_foot", lambda: foot_ini)
    terminal_grafico.definir(Capacidades(consultado=True, respondeu=True, nome="foot(1.28.0)"))
    executor.responder(["omarchy", "plugin", "list", "--json"], "[]")
    executor.responder(["hyprctl", "binds", "-j"], "[]")
    executor.responder(["omarchy", "theme", "list"], "A\nB\n")
    executor.responder(["omarchy", "theme", "set", "b"], "")
    executor.responder(["omarchy", "theme", "set", "a"], "")
    omarchy = OmarchyService(executor)
    a = OmarchyManagerApp(
        omarchy=omarchy, hyprland=HyprlandService(executor),
        catalogo=PluginCatalog(executor, raiz_usuario=tmp_path / "pu", raiz_sistema=tmp_path / "ps", traducoes={}),
        temas=ThemeService(omarchy, raiz_usuario=tmp_path / "tu", raiz_sistema=sistema, raiz_fundos_usuario=tmp_path / "tf", arquivo_config=tmp_path / "cfg.toml"),
        previa=PreviaAoVivo(omarchy, tmp_path / "st" / "previa.json"), aba_inicial="temas",
    )
    a.cores = estado / "theme" / "colors.toml"
    a.osc = []
    yield a
    terminal_grafico.definir(None)


async def _pronto(app, pilot):
    for _ in range(3):
        await pilot.pause()
        await app.workers.wait_for_complete()
    await pilot.pause()


def _espiar(app):
    original = app._driver.write

    def write(dados):
        if "\x1b]11;" in dados:
            app.osc.append(dados)
        return original(dados)

    app._driver.write = write


def _fundos(app):
    """Fundo efetivo da tela e dos contêineres principais (os que não têm cor própria)."""
    nomes = ["Screen", "#abas", "AbaTemas", "#temas-corpo", "#temas-previa", "#previa-info", "#previa-imagem"]
    saida = {}
    for n in nomes:
        w = app.screen if n == "Screen" else app.query_one(n)
        saida[n] = w.background_colors[1].hex.lower()[:7]
    return saida


async def test_fundo_acompanha_o_tema_e_alpha_e_reafirmado(app):
    async with app.run_test(size=(170, 45)) as pilot:
        await _pronto(app, pilot)
        _espiar(app)
        antes = _fundos(app)
        assert set(antes.values()) == {"#1a1b26"}  # tudo na cor de fundo do tema, que é o padrão do terminal

        app.cores.write_text(ESCURO_B)  # é o que `omarchy theme set` faz com o tema atual
        app.aplicar_paleta()
        await pilot.pause()
        depois = _fundos(app)
        assert set(depois.values()) == {"#0c0b0c"}, depois  # mesmo nome de tema Textual, cores novas
        assert depois.keys() == antes.keys()
        assert app.osc[-1] == "\x1b]11;[25]#0c0b0c\x07"

        app.cores.write_text(CLARO)
        app.aplicar_paleta()
        await pilot.pause()
        assert set(_fundos(app).values()) == {"#eff1f5"}  # tema claro: nenhum contêiner fica com cor própria
        assert app.osc[-1] == "\x1b]11;[25]#eff1f5\x07"


async def test_aplicar_tema_pela_aba_reafirma(app, executor):
    async with app.run_test(size=(170, 45)) as pilot:
        await _pronto(app, pilot)
        _espiar(app)
        tabela = app.query_one("#temas-tabela", DataTable)
        tabela.focus()
        tabela.move_cursor(row=tabela.get_row_index("b"))
        await pilot.pause()
        executor.responder(["omarchy", "theme", "set", "b"], "")
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, Confirmacao)
        app.cores.write_text(ESCURO_B)
        await pilot.press("l", "enter")
        await _pronto(app, pilot)
        assert ("omarchy", "theme", "set", "b") in executor.chamadas
        assert app.osc and app.osc[-1] == "\x1b]11;[25]#0c0b0c\x07"
        assert app.screen.background_colors[1].hex.lower()[:7] == "#0c0b0c"


async def test_previa_ao_vivo_e_restauracao_reafirmam(app, executor):
    async with app.run_test(size=(170, 45)) as pilot:
        await _pronto(app, pilot)
        _espiar(app)
        from omarchy_manager.ui.themes import AbaTemas

        aba = app.query_one(AbaTemas)
        aba.DEBOUNCE_PREVIA = 0.05
        tabela = app.query_one("#temas-tabela", DataTable)
        tabela.focus()
        tabela.move_cursor(row=tabela.get_row_index("b"))
        await pilot.press("v")
        await pilot.pause(0.3)
        await _pronto(app, pilot)
        n = len(app.osc)
        assert n >= 1
        await pilot.press("escape")
        await pilot.pause(0.3)
        await _pronto(app, pilot)
        assert len(app.osc) > n  # a restauração também reafirma


async def test_fora_do_foot_nao_envia_nada(app):
    terminal_grafico.definir(Capacidades(consultado=True, respondeu=True, nome="kitty(0.40)"))
    async with app.run_test(size=(170, 45)) as pilot:
        await _pronto(app, pilot)
        _espiar(app)
        app.aplicar_paleta()
        await pilot.pause()
        assert app.osc == []
