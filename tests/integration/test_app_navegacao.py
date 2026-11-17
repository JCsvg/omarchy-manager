"""Troca de abas (inclusive com o foco na pesquisa), aba Config, layout e prévia ao vivo."""

import pytest
from textual.widgets import DataTable, Input, Label, TabbedContent

from omarchy_manager.app import OmarchyManagerApp
from omarchy_manager.services import caminhos
from omarchy_manager.services.hyprland import HyprlandService
from omarchy_manager.services.omarchy import OmarchyService
from omarchy_manager.services.plugin_catalog import PluginCatalog
from omarchy_manager.services.previa_ao_vivo import PreviaAoVivo
from omarchy_manager.services.temas import ThemeService
from omarchy_manager.ui.themes import AbaTemas


@pytest.fixture
def app(tmp_path, executor, fixtures, monkeypatch):
    monkeypatch.setattr(caminhos, "PROIBIDOS", (tmp_path / "proibido",))
    monkeypatch.delenv("HYPRLAND_INSTANCE_SIGNATURE", raising=False)
    sistema = tmp_path / "sistema"
    for slug, cores in (("tokyo-night", "colors_dark.toml"), ("catppuccin-latte", "colors_light.toml"), ("signature", "colors_dark.toml")):
        (sistema / slug / "backgrounds").mkdir(parents=True)
        (sistema / slug / "colors.toml").write_text((fixtures / cores).read_text())
        (sistema / slug / "backgrounds" / "a.png").write_bytes(b"png")
    estado = tmp_path / "estado"
    estado.mkdir()
    (estado / "theme.name").write_text("signature\n")
    monkeypatch.setattr(caminhos, "OMARCHY_STATE_CURRENT", estado)
    executor.responder(["omarchy", "plugin", "list", "--json"], "[]")
    executor.responder(["hyprctl", "binds", "-j"], "[]")
    executor.responder(["omarchy", "theme", "list"], "Catppuccin Latte\nSignature\nTokyo Night\n")
    for slug in ("tokyo-night", "catppuccin-latte", "signature"):
        executor.responder(["omarchy", "theme", "set", slug], "")
    omarchy = OmarchyService(executor)
    return OmarchyManagerApp(
        omarchy=omarchy,
        hyprland=HyprlandService(executor),
        catalogo=PluginCatalog(executor, raiz_usuario=tmp_path / "p-u", raiz_sistema=tmp_path / "p-s", traducoes={}),
        temas=ThemeService(omarchy, raiz_usuario=tmp_path / "t-u", raiz_sistema=sistema, raiz_fundos_usuario=tmp_path / "t-f", arquivo_config=tmp_path / "cfg.toml"),
        previa=PreviaAoVivo(omarchy, tmp_path / "st" / "previa-original.json"),
    )


async def _pronto(app, pilot):
    for _ in range(3):
        await pilot.pause()
        await app.workers.wait_for_complete()
    await pilot.pause()


def _sets(executor):
    return [c[3] for c in executor.chamadas if c[:3] == ("omarchy", "theme", "set")]


async def test_alt_troca_de_aba_de_qualquer_foco(app):
    async with app.run_test(size=(150, 45)) as pilot:
        await _pronto(app, pilot)
        abas = app.query_one(TabbedContent)
        assert abas.active == "plugins"
        await pilot.press("alt+l")
        await pilot.pause()
        assert abas.active == "temas"
        await pilot.press("alt+right")
        await pilot.pause()
        assert abas.active == "config"
        await pilot.press("alt+l", "alt+l")
        await pilot.pause()
        assert abas.active == "terminal"
        await pilot.press("alt+l")
        await pilot.pause()
        assert abas.active == "atalhos"  # dá a volta
        await pilot.press("alt+h")
        await pilot.pause()
        assert abas.active == "terminal"
        await pilot.press("alt+left", "alt+left", "alt+left", "alt+left")
        await pilot.pause()
        assert abas.active == "plugins"

        # o caso que prendia: foco no campo de pesquisa. Dígito vira texto, Alt troca.
        await _pronto(app, pilot)  # deixa o foco assentar na tabela antes de ir para a pesquisa
        await pilot.press("slash")
        await pilot.pause()
        busca = app.query_one("#plugins-busca", Input)
        assert app.focused is busca
        await pilot.press("3")
        assert abas.active == "plugins" and busca.value == "3"
        await pilot.press("alt+l")
        await pilot.pause()
        assert abas.active == "temas"
        await pilot.press("4")
        await pilot.pause()
        assert abas.active == "config"
        assert app.query_one("#config-tabela", DataTable).row_count >= 20


async def test_clique_na_aba(app):
    async with app.run_test(size=(150, 45)) as pilot:
        await _pronto(app, pilot)
        abas = app.query_one(TabbedContent)
        for aba in ("temas", "config", "atalhos", "plugins"):
            await pilot.click(f"#--content-tab-{aba}")
            await pilot.pause()
            assert abas.active == aba


async def test_layout_duas_colunas_e_estreito(app):
    async with app.run_test(size=(170, 45)) as pilot:
        await _pronto(app, pilot)
        await pilot.press("3")
        await _pronto(app, pilot)
        aba = app.query_one(AbaTemas)
        assert not aba.has_class("estreito")
        info, imagem = app.query_one("#previa-info"), app.query_one("#previa-imagem")
        assert imagem.region.x >= info.region.right  # lado a lado
        assert imagem.region.right >= 165  # usa a largura até a borda direita
        colunas, linhas = aba._tamanho_miniatura()
        assert colunas >= 60 and linhas >= 15
        await pilot.resize_terminal(90, 40)
        await pilot.pause(0.5)
        assert aba.has_class("estreito")
        assert app.query_one("#previa-imagem").region.y >= app.query_one("#previa-info").region.y
        assert aba._tamanho_miniatura()[0] <= 84


async def test_previa_ao_vivo_aplica_e_restaura(app, executor):
    async with app.run_test(size=(170, 45)) as pilot:
        await _pronto(app, pilot)
        await pilot.press("3")
        await _pronto(app, pilot)
        aba = app.query_one(AbaTemas)
        aba.DEBOUNCE_PREVIA = 0.05
        tabela = app.query_one("#temas-tabela", DataTable)
        assert aba.tema_selecionado().slug == "signature"
        tabela.move_cursor(row=tabela.get_row_index("tokyo-night"))
        await pilot.pause()
        assert _sets(executor) == []  # sem prévia ligada, navegar não aplica nada

        await pilot.press("v")
        await pilot.pause(0.3)
        await _pronto(app, pilot)
        assert _sets(executor) == ["tokyo-night"] and app.previa.ativa
        assert "PRÉVIA AO VIVO" in str(app.query_one("#previa-modo", Label).render())
        assert app.previa.arquivo.is_file()

        tabela.move_cursor(row=tabela.get_row_index("catppuccin-latte"))
        await pilot.pause(0.3)
        await _pronto(app, pilot)
        assert _sets(executor) == ["tokyo-night", "catppuccin-latte"]

        await pilot.press("escape")
        await pilot.pause(0.2)
        await _pronto(app, pilot)
        assert _sets(executor)[-1] == "signature" and not app.previa.ativa and not app.previa.arquivo.exists()


async def test_trocar_de_aba_e_sair_restauram(app, executor):
    async with app.run_test(size=(170, 45)) as pilot:
        await _pronto(app, pilot)
        await pilot.press("3")
        await _pronto(app, pilot)
        aba = app.query_one(AbaTemas)
        aba.DEBOUNCE_PREVIA = 0.05
        tabela = app.query_one("#temas-tabela", DataTable)
        tabela.move_cursor(row=tabela.get_row_index("tokyo-night"))
        await pilot.press("v")
        await pilot.pause(0.3)
        await _pronto(app, pilot)
        assert app.previa.ativa
        await pilot.press("alt+h")
        await pilot.pause(0.2)
        await _pronto(app, pilot)
        assert _sets(executor) == ["tokyo-night", "signature"] and not app.previa.ativa

        await pilot.press("3")
        await _pronto(app, pilot)
        tabela.move_cursor(row=tabela.get_row_index("tokyo-night"))
        await pilot.press("v")
        await pilot.pause(0.3)
        await _pronto(app, pilot)
        assert app.previa.ativa
        await pilot.press("q")
        await pilot.pause()
    assert _sets(executor)[-1] == "signature" and not app.previa.arquivo.exists()


async def test_ctrl_segurado_aplica_e_soltar_restaura(app, executor):
    async with app.run_test(size=(170, 45)) as pilot:
        await _pronto(app, pilot)
        await pilot.press("3")
        await _pronto(app, pilot)
        aba = app.query_one(AbaTemas)
        aba.DEBOUNCE_PREVIA = 0.05
        aba._sondar = False  # o teste entrega o estado do Ctrl à mão
        tabela = app.query_one("#temas-tabela", DataTable)
        tabela.move_cursor(row=tabela.get_row_index("tokyo-night"))
        await pilot.pause()
        aba._ctrl_mudou(True)
        await pilot.pause(0.3)
        await _pronto(app, pilot)
        assert _sets(executor) == ["tokyo-night"]
        aba._ctrl_mudou(False)
        await pilot.pause(0.2)
        await _pronto(app, pilot)
        assert _sets(executor) == ["tokyo-night", "signature"] and not app.previa.ativa


async def test_toque_rapido_no_ctrl_nao_aplica(app, executor):
    async with app.run_test(size=(170, 45)) as pilot:
        await _pronto(app, pilot)
        await pilot.press("3")
        await _pronto(app, pilot)
        aba = app.query_one(AbaTemas)
        aba._sondar = False
        tabela = app.query_one("#temas-tabela", DataTable)
        tabela.move_cursor(row=tabela.get_row_index("tokyo-night"))
        aba._ctrl_mudou(True)
        await pilot.pause(0.1)  # menos que o debounce de 0,5 s
        aba._ctrl_mudou(False)
        await pilot.pause(0.7)
        await _pronto(app, pilot)
        assert _sets(executor) == []


async def test_abas_fundo_e_terminal_existem_e_abrem(app, tmp_path, monkeypatch):
    from omarchy_manager.services import terminal_cfg

    foot = tmp_path / "foot.ini"
    foot.write_text("[main]\nfont=Fira Code:size=9\npad=5x5\n")
    monkeypatch.setattr(terminal_cfg, "arquivo_foot", lambda: foot)
    monkeypatch.setattr(terminal_cfg, "terminal_padrao", lambda: "foot")
    async with app.run_test(size=(150, 45)) as pilot:
        await _pronto(app, pilot)
        await pilot.press("5")
        await _pronto(app, pilot)
        assert app.query_one(TabbedContent).active == "fundo"
        await pilot.press("6")
        await _pronto(app, pilot)
        assert app.query_one(TabbedContent).active == "terminal"
        assert app.query_one("#term-fonte").value == "Fira Code"
        assert app.query_one("#term-margem").value == "5"


async def test_ctrl_setas_andam_entre_botoes_e_ctrl_enter_aperta(app, tmp_path, monkeypatch):
    from textual.widgets import Button

    from omarchy_manager.services import terminal_cfg

    monkeypatch.setattr(terminal_cfg, "arquivo_foot", lambda: tmp_path / "foot.ini")
    async with app.run_test(size=(150, 45)) as pilot:
        await _pronto(app, pilot)
        await pilot.press("6")
        await _pronto(app, pilot)
        await pilot.press("ctrl+right")
        assert isinstance(app.focused, Button) and app.focused.id == "term-aplicar"
        await pilot.press("ctrl+right")
        assert app.focused.id == "term-desfazer"
        await pilot.press("ctrl+left", "ctrl+left")
        assert app.focused.id == "term-prompt-restaurar"  # dá a volta
        await pilot.press("ctrl+left", "ctrl+left", "ctrl+left")
        await pilot.press("ctrl+enter")
        await pilot.pause()
        assert "foot.ini" in str(app.query_one("#term-status").render())
