"""Tela de abertura: uma vez por boot, some com tecla, clique e tempo, opção na Config."""

import asyncio
from pathlib import Path

import pytest
from textual.widgets import Checkbox

from omarchy_manager.app import OmarchyManagerApp
from omarchy_manager.services import abertura as ab
from omarchy_manager.services.hyprland import HyprlandService
from omarchy_manager.services.omarchy import OmarchyService
from omarchy_manager.services.plugin_catalog import PluginCatalog
from omarchy_manager.services.previa_ao_vivo import PreviaAoVivo
from omarchy_manager.services.temas import ThemeService
from omarchy_manager.ui.abertura import Abertura, banner


@pytest.fixture
def boot(tmp_path, monkeypatch):
    """Um boot novo: runtime dir de teste sem marcador."""
    pasta = tmp_path / "run"
    pasta.mkdir()
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(pasta))
    return pasta


def _app(tmp_path, executor, aba_inicial="plugins"):
    executor.responder(["omarchy", "plugin", "list", "--json"], "[]")
    executor.responder(["hyprctl", "binds", "-j"], "[]")
    executor.responder(["omarchy", "theme", "list"], "Signature\n")
    omarchy = OmarchyService(executor)
    return OmarchyManagerApp(
        omarchy=omarchy, hyprland=HyprlandService(executor),
        catalogo=PluginCatalog(executor, raiz_usuario=tmp_path / "p-u", raiz_sistema=tmp_path / "p-s", traducoes={}),
        temas=ThemeService(omarchy, raiz_usuario=tmp_path / "t-u", raiz_sistema=tmp_path / "sistema", raiz_fundos_usuario=tmp_path / "t-f", arquivo_config=tmp_path / "cfg.toml"),
        previa=PreviaAoVivo(omarchy, tmp_path / "st" / "previa-original.json"),
        aba_inicial=aba_inicial,
    )


def _abertura_aberta(app) -> bool:
    return isinstance(app.screen, Abertura)


async def test_aparece_uma_vez_por_boot(tmp_path, executor, boot):
    app = _app(tmp_path, executor)
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        assert _abertura_aberta(app)
    assert (boot / "omarchy-manager" / "abertura-mostrada").exists()
    app2 = _app(tmp_path, executor)
    async with app2.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        assert not _abertura_aberta(app2)


async def test_some_com_tecla(tmp_path, executor, boot):
    app = _app(tmp_path, executor)
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        await pilot.press("x")
        await pilot.pause()
        assert not _abertura_aberta(app)


async def test_some_com_clique(tmp_path, executor, boot):
    app = _app(tmp_path, executor)
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        await pilot.click(offset=(5, 5))
        await pilot.pause()
        assert not _abertura_aberta(app)


async def test_some_com_o_tempo(tmp_path, executor, boot):
    app = _app(tmp_path, executor)
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        assert _abertura_aberta(app)
        await asyncio.sleep(1.8)
        await pilot.pause()
        assert not _abertura_aberta(app)


async def test_nao_aparece_com_a_opcao_desligada(tmp_path, executor, boot):
    ab.definir_abertura_ativa(False)
    app = _app(tmp_path, executor)
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        assert not _abertura_aberta(app)
    assert not (boot / "omarchy-manager" / "abertura-mostrada").exists()


async def test_marcador_corrompido_e_ignorado(tmp_path, executor, boot):
    (boot / "omarchy-manager").mkdir()
    (boot / "omarchy-manager" / "abertura-mostrada").write_bytes(b"\xff\xfe\x00lixo")
    app = _app(tmp_path, executor)
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        assert _abertura_aberta(app)


async def test_marcador_que_e_pasta_nao_quebra(tmp_path, executor, boot):
    (boot / "omarchy-manager" / "abertura-mostrada").mkdir(parents=True)
    assert ab.ja_mostrou() is False
    ab.marcar()  # não levanta


def test_sem_runtime_dir_mostra_sem_erro(monkeypatch):
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    assert ab.ja_mostrou() is False
    ab.marcar()


@pytest.mark.parametrize("tam,esperado", [((80, 24), 2), ((120, 30), 1), ((200, 50), 1), ((30, 6), 0)])
def test_banner_nos_tamanhos(tam, esperado):
    linhas = banner(*tam)
    if esperado == 1:
        assert len(linhas) == 5 and max(len(l) for l in linhas) <= tam[0]
    elif esperado == 2:
        assert len(linhas) == 11 and max(len(l) for l in linhas) <= tam[0]
    else:
        assert linhas == ["OMARCHY MANAGER"]


@pytest.mark.parametrize("tam", [(80, 24), (120, 30), (200, 50), (40, 8)])
async def test_abertura_renderiza_nos_tamanhos(tmp_path, executor, boot, tam):
    app = _app(tmp_path, executor)
    async with app.run_test(size=tam) as pilot:
        await pilot.pause()
        assert _abertura_aberta(app)


async def test_opcao_na_config_por_clique_e_teclado(tmp_path, executor, boot):
    app = _app(tmp_path, executor, aba_inicial="config")
    async with app.run_test(size=(170, 45)) as pilot:
        await pilot.press("x")
        await pilot.pause()
        caixa = app.query_one("#config-abertura", Checkbox)
        assert caixa.value is True and ab.abertura_ativa()
        await pilot.click("#config-abertura")
        await pilot.pause()
        assert caixa.value is False and not ab.abertura_ativa()
        caixa.focus()
        await pilot.press("space")
        await pilot.pause()
        assert caixa.value is True and ab.abertura_ativa()
