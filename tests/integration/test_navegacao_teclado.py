"""Navegação só por teclado: toda tela alcançável com Ctrl+j/k e Ctrl+h/l, sem Tab nem mouse."""

import pytest
from textual.widgets import Button

from omarchy_manager.ui.navegacao import eh_controle

from omarchy_manager.app import OmarchyManagerApp
from omarchy_manager.services import caminhos
from omarchy_manager.services.hyprland import HyprlandService
from omarchy_manager.services.omarchy import OmarchyService
from omarchy_manager.services.plugin_catalog import PluginCatalog
from omarchy_manager.services.previa_ao_vivo import PreviaAoVivo
from omarchy_manager.services.temas import ThemeService


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


def _focaveis(aba):
    return [w for w in aba.query("*") if eh_controle(w)]


@pytest.mark.parametrize("aba_id", ["atalhos", "plugins", "temas", "config", "fundo", "terminal", "compartilhar", "webapps"])
async def test_toda_aba_alcancavel_so_com_o_esquema(app, aba_id):
    async with app.run_test(size=(160, 60)) as pilot:
        await _pronto(app, pilot)
        app.action_aba(aba_id)
        await _pronto(app, pilot)
        aba = app.query_one(app.aba_ativa())
        esperados = {id(w) for w in _focaveis(aba)}
        assert esperados, "aba sem nada focável"
        visitados = set()
        # Ctrl+j anda zona a zona (e Esc volta para a lista); Ctrl+l percorre a fileira de botões.
        await pilot.press("escape")
        for _ in range(len(aba.zonas()) + 1):
            await pilot.press("ctrl+k")  # até a primeira zona
        await pilot.pause()
        for _ in range(len(aba.zonas()) + 2):
            if app.focused is not None:
                visitados.add(id(app.focused))
                if isinstance(app.focused, Button) or len(aba.fileira()) > 1:
                    for _ in range(len(aba.fileira()) or 4):
                        await pilot.press("ctrl+l")
                        visitados.add(id(app.focused))
            await pilot.press("ctrl+j")
            await pilot.pause()
        faltam = [w.id for w in _focaveis(aba) if id(w) not in visitados]
        assert not faltam, f"inalcançável só com teclado: {faltam}"


async def test_dialogo_alcancavel_so_com_o_esquema(app):
    from omarchy_manager.ui.compartilhar import ListaRemota, PedirCaminho

    async with app.run_test(size=(160, 60)) as pilot:
        await _pronto(app, pilot)
        for tela in (PedirCaminho("t", "d"), ListaRemota([{"id": "1", "tipo": "pasta", "nome": "x", "tamanho": 10}], "ip")):
            app.push_screen(tela)
            await _pronto(app, pilot)
            esperados = {w.id for w in tela.query("*") if eh_controle(w)}
            visitados = set()
            for _ in range(len(esperados) + 2):
                visitados.add(app.focused.id)
                await pilot.press("ctrl+j")
                await pilot.pause()
            for _ in range(4):
                await pilot.press("ctrl+l")
                visitados.add(app.focused.id)
            assert esperados <= visitados, esperados - visitados
            app.pop_screen()
            await pilot.pause()
