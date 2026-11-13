"""Integração: aba Atalhos com `hyprctl` falso, varredura Lua real sobre um
hyprland.lua sintético, gravação em diretórios temporários e rollback."""

from pathlib import Path

import pytest
from textual.widgets import DataTable

from omarchy_manager.app import OmarchyManagerApp
from omarchy_manager.services import caminhos
from omarchy_manager.services.executor import executar
from omarchy_manager.services.hyprland import HyprlandService
from omarchy_manager.services.omarchy import OmarchyService
from omarchy_manager.services.overrides import GerenciadorOverrides
from omarchy_manager.services.plugin_catalog import PluginCatalog
from omarchy_manager.services.shortcut_capture import CapturaHyprland
from omarchy_manager.services.temas import ThemeService
from omarchy_manager.ui.dialogs import Confirmacao
from omarchy_manager.ui.shortcuts import AbaAtalhos, CapturaTecla

HYPRLAND_LUA = """
hl.bind("SUPER + W", hl.dsp.exec_cmd("omarchy-close"), { description = "Close window" })
hl.bind("SUPER + SPACE", hl.dsp.exec_cmd("omarchy-menu toggle root"), { description = "Omarchy menu" })
hl.bind("SUPER + SHIFT + code:59", hl.dsp.exec_cmd("/home/jc/.local/bin/op less"), { description = "Diminuir transparência da janela" })
hl.bind("ALT + TAB", hl.dsp.window.cycle(), { description = "Reveal active window" })
hl.bind("ALT + TAB", hl.dsp.exec_cmd("antigo"), { description = "Antigo Alt+Tab" })
hl.bind("XF86AudioRaiseVolume", hl.dsp.exec_cmd("omarchy-shell shell toggle omarchy.audio"), { description = "Volume up" })
"""


def _executor_misto(executor):
    def fn(args, **kw):
        if args[0] == "lua":
            return executar(args, **kw)
        return executor(args, **kw)

    return fn


@pytest.fixture
def app(tmp_path, executor, fixtures, monkeypatch):
    hypr = tmp_path / "hypr"
    hypr.mkdir()
    (hypr / "hyprland.lua").write_text(HYPRLAND_LUA)
    (hypr / "bindings.lua").write_text("-- do usuário\n")
    monkeypatch.setattr(caminhos, "HYPR_DIR", hypr)
    monkeypatch.setattr(caminhos, "HYPR_BINDINGS", hypr / "bindings.lua")
    monkeypatch.setattr(caminhos, "HYPR_MANAGER_BINDINGS", hypr / "omarchy-manager-bindings.lua")
    monkeypatch.setattr(caminhos, "PROIBIDOS", (tmp_path / "proibido",))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setenv("OMARCHY_PATH", str(tmp_path / "proibido"))
    monkeypatch.delenv("HYPRLAND_INSTANCE_SIGNATURE", raising=False)
    monkeypatch.setattr("omarchy_manager.services.lua_scan.executar", _executor_misto(executor))

    executor.responder(["omarchy", "plugin", "list", "--json"], "[]")
    executor.responder(["omarchy", "theme", "list"], "")
    executor.responder(["hyprctl", "binds", "-j"], (fixtures / "binds.json").read_text())
    executor.responder(["hyprctl", "reload"], "ok")
    executor.responder(["hyprctl", "configerrors"], "\n")
    omarchy = OmarchyService(executor)
    hyprland = HyprlandService(executor)
    return OmarchyManagerApp(
        omarchy=omarchy,
        hyprland=hyprland,
        catalogo=PluginCatalog(executor, raiz_usuario=tmp_path / "p-u", raiz_sistema=tmp_path / "p-s"),
        temas=ThemeService(omarchy, raiz_usuario=tmp_path / "t-u", raiz_sistema=tmp_path / "t-s", raiz_fundos_usuario=tmp_path / "t-f", arquivo_config=tmp_path / "cfg.toml"),
        overrides=GerenciadorOverrides(
            hyprland,
            arquivo=hypr / "omarchy-manager-bindings.lua",
            bindings_usuario=hypr / "bindings.lua",
            pasta_backups=tmp_path / "backups",
            executar_fn=_executor_misto(executor),
        ),
        captura=CapturaHyprland(hyprland, arquivo=tmp_path / "troca.txt"),
    )


async def _pronto(app, pilot):
    await pilot.pause()
    await app.workers.wait_for_complete()
    await pilot.pause()


async def _selecionar(app, pilot, descricao):
    aba = app.query_one(AbaAtalhos)
    tabela = app.query_one("#atalhos-tabela", DataTable)
    tabela.focus()
    indice = next(i for i, a in aba._por_linha.items() if a.description == descricao)
    tabela.move_cursor(row=tabela.get_row_index(str(indice)))
    await pilot.pause()
    assert aba.atalho_selecionado().description == descricao


async def test_lista_com_origem_comando_e_duplicados(app):
    async with app.run_test(size=(150, 45)) as pilot:
        await _pronto(app, pilot)
        await pilot.press("1")
        await _pronto(app, pilot)
        aba = app.query_one(AbaAtalhos)
        por_desc = {a.description: a for a in aba.atalhos}
        assert por_desc["Close window"].comando == "omarchy-close"
        assert por_desc["Close window"].origem == "usuario"
        assert por_desc["Diminuir transparência da janela"].combinacao == "SUPER + SHIFT + code:59"
        assert por_desc["Reveal active window"].duplicado and por_desc["Antigo Alt+Tab"].duplicado
        assert por_desc["Reveal active window"].comando == "hl.dsp.window.cycle()"
        assert app.query_one("#atalhos-tabela", DataTable).row_count == 6


async def test_filtro_por_plugin(app):
    async with app.run_test(size=(150, 45)) as pilot:
        await _pronto(app, pilot)
        app.ir_para_atalhos_do_plugin("omarchy.audio")
        await _pronto(app, pilot)
        tabela = app.query_one("#atalhos-tabela", DataTable)
        assert tabela.row_count == 1
        await pilot.press("escape")
        await pilot.pause()
        assert tabela.row_count == 6


async def test_editar_livre_grava_e_recarrega(app, executor, tmp_path):
    async with app.run_test(size=(150, 45)) as pilot:
        await _pronto(app, pilot)
        await pilot.press("1")
        await _pronto(app, pilot)
        await _selecionar(app, pilot, "Close window")
        await pilot.press("e")
        await pilot.pause()
        assert isinstance(app.screen, CapturaTecla)
        await pilot.press("ctrl+alt+w")
        await pilot.pause()
        assert isinstance(app.screen, Confirmacao)
        assert "livre" in app.screen._titulo
        await pilot.click("#ok")
        await _pronto(app, pilot)
        gerado = (tmp_path / "hypr" / "omarchy-manager-bindings.lua").read_text()
        assert 'hl.unbind("SUPER + W")' in gerado
        assert 'o.bind("CTRL + ALT + W", "Close window", "omarchy-close")' in gerado
        assert "omarchy-manager" in (tmp_path / "hypr" / "bindings.lua").read_text()
        assert ("hyprctl", "reload") in executor.chamadas and ("hyprctl", "configerrors") in executor.chamadas


async def test_conflito_avisa_e_cancela(app, tmp_path):
    async with app.run_test(size=(150, 45)) as pilot:
        await _pronto(app, pilot)
        await pilot.press("1")
        await _pronto(app, pilot)
        await _selecionar(app, pilot, "Omarchy menu")
        await pilot.press("e")
        await pilot.pause()
        await pilot.press("super+w")
        await pilot.pause()
        assert isinstance(app.screen, Confirmacao)
        assert "já usado" in app.screen._titulo and "Close window" in app.screen._mensagem
        await pilot.press("escape")
        await _pronto(app, pilot)
        assert not (tmp_path / "hypr" / "omarchy-manager-bindings.lua").exists()


async def test_erro_do_hyprland_faz_rollback(app, executor, tmp_path):
    executor.responder(["hyprctl", "configerrors"], "config error: boom\n")
    async with app.run_test(size=(150, 45)) as pilot:
        await _pronto(app, pilot)
        await pilot.press("1")
        await _pronto(app, pilot)
        await _selecionar(app, pilot, "Close window")
        await pilot.press("e")
        await pilot.pause()
        await pilot.press("ctrl+alt+w")
        await pilot.pause()
        await pilot.click("#ok")
        await _pronto(app, pilot)
        assert not (tmp_path / "hypr" / "omarchy-manager-bindings.lua").exists()
        assert executor.chamadas.count(("hyprctl", "reload")) >= 2
