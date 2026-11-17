"""Integração: a aba Plugins contra `omarchy` e `git` falsos (fixtures)."""

import json

import pytest
from textual.widgets import Button, DataTable, TabbedContent

from omarchy_manager.app import OmarchyManagerApp
from omarchy_manager.services.hyprland import HyprlandService
from omarchy_manager.services.omarchy import OmarchyService
from omarchy_manager.services.plugin_catalog import PluginCatalog
from omarchy_manager.services.temas import ThemeService
from omarchy_manager.ui.dialogs import Aviso, Confirmacao
from omarchy_manager.ui.plugins import AbaPlugins


def _raizes(tmp_path):
    sistema, usuario = tmp_path / "sistema", tmp_path / "usuario"
    for raiz, pasta, pid, extra in (
        (sistema, "clipboard", "omarchy.clipboard", {"description": "Histórico", "author": "Omarchy", "version": "1"}),
        (sistema, "bar", "omarchy.bar", {}),
        (usuario, "io.github.nipsen.dell-power", "io.github.nipsen.dell-power", {"repository": "https://github.com/NIPSEN/omarchy-dell-power.git", "version": "1.4.1"}),
        (usuario, "bibek.lock", "bibek.lock", {}),
    ):
        (raiz / pasta).mkdir(parents=True, exist_ok=True)
        (raiz / pasta / "manifest.json").write_text(json.dumps({"id": pid, "name": pid, **extra}))
    return sistema, usuario


@pytest.fixture
def app(tmp_path, executor, fixtures):
    sistema, usuario = _raizes(tmp_path)
    executor.responder(["omarchy", "plugin", "list", "--json"], (fixtures / "plugin_list.json").read_text())
    executor.responder(["omarchy", "plugin", "disable", "omarchy.clipboard"], "ok")
    executor.responder(["omarchy", "plugin", "enable", "omarchy.bar"], "ok")
    executor.responder(["omarchy", "plugin", "remove", "io.github.nipsen.dell-power", "--yes"], "removed")
    executor.responder(["hyprctl", "binds", "-j"], "[]")
    executor.responder(["omarchy", "theme", "list"], "")
    omarchy = OmarchyService(executor)
    return OmarchyManagerApp(
        omarchy=omarchy,
        hyprland=HyprlandService(executor),
        catalogo=PluginCatalog(executor, raiz_usuario=usuario, raiz_sistema=sistema, traducoes={}),
        temas=ThemeService(
            omarchy,
            raiz_usuario=tmp_path / "t-usuario",
            raiz_sistema=tmp_path / "t-sistema",
            raiz_fundos_usuario=tmp_path / "t-fundos",
            arquivo_config=tmp_path / "cfg" / "config.toml",
        ),
    )


async def _pronto(app, pilot):
    await pilot.pause()
    await app.workers.wait_for_complete()
    await pilot.pause()


async def _ir_para(app, pilot, plugin_id):
    tabela = app.query_one("#plugins-tabela", DataTable)
    tabela.focus()
    tabela.move_cursor(row=tabela.get_row_index(plugin_id))
    await pilot.pause()
    assert app.query_one(AbaPlugins).plugin_selecionado().id == plugin_id


async def test_abas_e_listagem(app, executor):
    async with app.run_test(size=(120, 40)) as pilot:
        await _pronto(app, pilot)
        abas = app.query_one(TabbedContent)
        assert [p.id for p in abas.query("TabPane")] == ["atalhos", "plugins", "temas", "config", "fundo", "terminal"]
        assert abas.active == "plugins"
        tabela = app.query_one("#plugins-tabela", DataTable)
        assert tabela.row_count == 5
        await pilot.press("1")
        assert abas.active == "atalhos"
        await pilot.press("3")
        assert abas.active == "temas"
        assert ("omarchy", "plugin", "list", "--json") in executor.chamadas


async def test_ligar_e_desligar(app, executor):
    async with app.run_test(size=(120, 40)) as pilot:
        await _pronto(app, pilot)
        await _ir_para(app, pilot, "omarchy.clipboard")
        assert str(app.query_one("#btn-alternar", Button).label) == "Desligar"
        await pilot.press("space")
        await _pronto(app, pilot)
        assert ("omarchy", "plugin", "disable", "omarchy.clipboard") in executor.chamadas

        await _ir_para(app, pilot, "omarchy.bar")
        assert str(app.query_one("#btn-alternar", Button).label) == "Ligar"
        await pilot.click("#btn-alternar")
        await _pronto(app, pilot)
        assert ("omarchy", "plugin", "enable", "omarchy.bar") in executor.chamadas


async def test_nativo_nunca_recebe_remocao(app, executor):
    async with app.run_test(size=(120, 40)) as pilot:
        await _pronto(app, pilot)
        await _ir_para(app, pilot, "omarchy.clipboard")
        assert app.query_one("#btn-desinstalar", Button).disabled
        await pilot.press("d")
        await pilot.pause()
        assert isinstance(app.screen, Aviso)
        await pilot.press("escape")
        await _pronto(app, pilot)
        assert not any(c[:3] == ("omarchy", "plugin", "remove") for c in executor.chamadas)


async def test_terceiro_remove_so_apos_confirmar(app, executor):
    async with app.run_test(size=(120, 40)) as pilot:
        await _pronto(app, pilot)
        await _ir_para(app, pilot, "io.github.nipsen.dell-power")
        assert not app.query_one("#btn-desinstalar", Button).disabled
        assert not app.query_one("#btn-github", Button).disabled

        await pilot.press("d")
        await pilot.pause()
        assert isinstance(app.screen, Confirmacao)
        await pilot.press("escape")
        await _pronto(app, pilot)
        assert not any(c[:3] == ("omarchy", "plugin", "remove") for c in executor.chamadas)

        await pilot.press("d")
        await pilot.pause()
        await pilot.click("#ok")
        await _pronto(app, pilot)
        assert ("omarchy", "plugin", "remove", "io.github.nipsen.dell-power", "--yes") in executor.chamadas


async def test_busca_filtra(app):
    async with app.run_test(size=(120, 40)) as pilot:
        await _pronto(app, pilot)
        await pilot.press("slash")
        await pilot.press(*"dell")
        await pilot.pause()
        tabela = app.query_one("#plugins-tabela", DataTable)
        assert tabela.row_count == 1
        await pilot.press("escape")
        await pilot.pause()
        assert tabela.row_count == 5
