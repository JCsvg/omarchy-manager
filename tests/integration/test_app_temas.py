"""Integração: aba Temas com `omarchy` falso, temas em diretórios temporários."""

import pytest
from textual.widgets import DataTable, Static

from omarchy_manager.app import OmarchyManagerApp
from omarchy_manager.services import caminhos
from omarchy_manager.services.hyprland import HyprlandService
from omarchy_manager.services.omarchy import OmarchyService
from omarchy_manager.services.plugin_catalog import PluginCatalog
from omarchy_manager.services.temas import ThemeService
from omarchy_manager.ui.dialogs import Confirmacao
from omarchy_manager.ui.themes import AbaTemas, EscolherFundo


@pytest.fixture
def app(tmp_path, executor, fixtures, monkeypatch):
    sistema, usuario, fundos = tmp_path / "sistema", tmp_path / "usuario", tmp_path / "fundos"
    for raiz, slug, cores in (
        (sistema, "tokyo-night", "colors_dark.toml"),
        (sistema, "catppuccin-latte", "colors_light.toml"),
        (usuario, "signature", "colors_dark.toml"),
    ):
        (raiz / slug / "backgrounds").mkdir(parents=True)
        (raiz / slug / "colors.toml").write_text((fixtures / cores).read_text())
        (raiz / slug / "backgrounds" / "a.png").write_bytes(b"png")
    estado = tmp_path / "estado"
    estado.mkdir()
    (estado / "theme.name").write_text("signature\n")
    monkeypatch.setattr(caminhos, "OMARCHY_STATE_CURRENT", estado)

    executor.responder(["omarchy", "plugin", "list", "--json"], "[]")
    executor.responder(["hyprctl", "binds", "-j"], "[]")
    executor.responder(["omarchy", "theme", "list"], "Catppuccin Latte\nSignature\nTokyo Night\n")
    executor.responder(["omarchy", "theme", "set", "tokyo-night"], "")
    executor.responder(["omarchy", "theme", "bg", "set", str((sistema / "tokyo-night" / "backgrounds" / "a.png").resolve())], "")
    omarchy = OmarchyService(executor)
    return OmarchyManagerApp(
        omarchy=omarchy,
        hyprland=HyprlandService(executor),
        catalogo=PluginCatalog(executor, raiz_usuario=tmp_path / "p-u", raiz_sistema=tmp_path / "p-s"),
        temas=ThemeService(
            omarchy,
            raiz_usuario=usuario,
            raiz_sistema=sistema,
            raiz_fundos_usuario=fundos,
            arquivo_config=tmp_path / "cfg" / "config.toml",
        ),
    )


async def _pronto(app, pilot):
    await pilot.pause()
    await app.workers.wait_for_complete()
    await pilot.pause()


async def _ir_para(app, pilot, slug):
    tabela = app.query_one("#temas-tabela", DataTable)
    tabela.focus()
    tabela.move_cursor(row=tabela.get_row_index(slug))
    await pilot.pause()
    assert app.query_one(AbaTemas).tema_selecionado().slug == slug


async def test_lista_marca_atual_e_mostra_previa(app):
    async with app.run_test(size=(140, 45)) as pilot:
        await _pronto(app, pilot)
        await pilot.press("3")
        await _pronto(app, pilot)
        aba = app.query_one(AbaTemas)
        tabela = app.query_one("#temas-tabela", DataTable)
        assert tabela.row_count == 3
        assert aba.tema_selecionado().slug == "signature"
        await _ir_para(app, pilot, "catppuccin-latte")
        paleta = app.query_one("#previa-paleta", Static)
        assert "modo claro" in str(paleta.render())
        assert "#eff1f5" in str(paleta.render())


async def test_aplicar_pede_confirmacao_e_aplica_fundo_padrao(app, executor, tmp_path):
    async with app.run_test(size=(140, 45)) as pilot:
        await _pronto(app, pilot)
        await pilot.press("3")
        await _pronto(app, pilot)
        await _ir_para(app, pilot, "tokyo-night")

        # define a imagem padrão pelo diálogo
        await pilot.press("p")
        await pilot.pause()
        assert isinstance(app.screen, EscolherFundo)
        await pilot.press("down", "enter")
        await _pronto(app, pilot)
        assert app.temas.fundos_padrao().keys() == {"tokyo-night"}

        await _ir_para(app, pilot, "tokyo-night")
        await pilot.click("#btn-aplicar")
        await pilot.pause()
        assert isinstance(app.screen, Confirmacao)
        await pilot.press("escape")
        await _pronto(app, pilot)
        assert not any(c[:3] == ("omarchy", "theme", "set") for c in executor.chamadas)

        await pilot.click("#btn-aplicar")
        await pilot.pause()
        await pilot.click("#ok")
        await _pronto(app, pilot)
        assert ("omarchy", "theme", "set", "tokyo-night") in executor.chamadas
        assert any(c[:4] == ("omarchy", "theme", "bg", "set") for c in executor.chamadas)
