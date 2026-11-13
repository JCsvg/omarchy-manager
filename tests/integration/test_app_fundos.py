"""h/l e setas trocam o fundo exibido; o exibido vira o padrão, com debounce. Tudo em diretórios temporários."""

import pytest
from textual.widgets import DataTable, Input, Label, Static, TabbedContent

from omarchy_manager.app import OmarchyManagerApp
from omarchy_manager.services import caminhos
from omarchy_manager.services.hyprland import HyprlandService
from omarchy_manager.services.omarchy import OmarchyService
from omarchy_manager.services.plugin_catalog import PluginCatalog
from omarchy_manager.services.previa_ao_vivo import PreviaAoVivo
from omarchy_manager.services.temas import ThemeService
from omarchy_manager.ui.themes import AbaTemas, EscolherFundo


@pytest.fixture
def app(tmp_path, executor, fixtures, monkeypatch):
    monkeypatch.setattr(caminhos, "PROIBIDOS", (tmp_path / "proibido",))
    monkeypatch.delenv("HYPRLAND_INSTANCE_SIGNATURE", raising=False)
    sistema = tmp_path / "sistema"
    for slug, fundos in (("signature", ("a.png", "b.png", "c.png")), ("solo", ("unico.png",)), ("vazio", ())):
        (sistema / slug / "backgrounds").mkdir(parents=True)
        (sistema / slug / "colors.toml").write_text((fixtures / "colors_dark.toml").read_text())
        for f in fundos:
            (sistema / slug / "backgrounds" / f).write_bytes(b"png")
    estado = tmp_path / "estado"
    estado.mkdir()
    (estado / "theme.name").write_text("solo\n")
    monkeypatch.setattr(caminhos, "OMARCHY_STATE_CURRENT", estado)
    executor.responder(["omarchy", "plugin", "list", "--json"], "[]")
    executor.responder(["hyprctl", "binds", "-j"], "[]")
    executor.responder(["omarchy", "theme", "list"], "Signature\nSolo\nVazio\n")
    for slug in ("signature", "solo"):
        executor.responder(["omarchy", "theme", "set", slug], "")
    for f in ("a.png", "b.png", "c.png"):
        executor.responder(["omarchy", "theme", "bg", "set", str((sistema / "signature" / "backgrounds" / f).resolve())], "")
    omarchy = OmarchyService(executor)
    a = OmarchyManagerApp(
        omarchy=omarchy,
        hyprland=HyprlandService(executor),
        catalogo=PluginCatalog(executor, raiz_usuario=tmp_path / "p-u", raiz_sistema=tmp_path / "p-s", traducoes={}),
        temas=ThemeService(omarchy, raiz_usuario=tmp_path / "t-u", raiz_sistema=sistema, raiz_fundos_usuario=tmp_path / "t-f", arquivo_config=tmp_path / "cfg" / "config.toml"),
        previa=PreviaAoVivo(omarchy, tmp_path / "st" / "previa-original.json"),
        aba_inicial="temas",
    )
    a.cfg = tmp_path / "cfg" / "config.toml"
    return a


async def _pronto(app, pilot):
    for _ in range(3):
        await pilot.pause()
        await app.workers.wait_for_complete()
    await pilot.pause()


async def _ir(app, pilot, slug):
    tabela = app.query_one("#temas-tabela", DataTable)
    tabela.focus()
    tabela.move_cursor(row=tabela.get_row_index(slug))
    await pilot.pause()
    return app.query_one(AbaTemas)


def _info(app):
    return str(app.query_one("#previa-fundo-info", Static).render())


def _bg(executor):
    return [c for c in executor.chamadas if c[:4] == ("omarchy", "theme", "bg", "set")]


async def test_ciclo_posicao_e_padrao_automatico(app, executor):
    async with app.run_test(size=(170, 45)) as pilot:
        await _pronto(app, pilot)
        aba = await _ir(app, pilot, "signature")
        aba.DEBOUNCE_PADRAO = 0.15
        assert "a.png" in _info(app) and "1 de 3" in _info(app) and "sem padrão" in _info(app)

        await pilot.press("l")
        await pilot.pause()
        assert "b.png" in _info(app) and "2 de 3" in _info(app) and "gravando" in _info(app)
        assert not app.cfg.exists()  # ainda não assentou
        await pilot.press("right")
        await pilot.pause()
        assert "c.png" in _info(app) and "3 de 3" in _info(app)
        await pilot.press("l")  # dá a volta
        await pilot.pause()
        assert "a.png" in _info(app) and "1 de 3" in _info(app)
        await pilot.press("h")
        await pilot.press("left")
        await pilot.pause()
        assert "b.png" in _info(app)
        assert not app.cfg.exists()  # passada rápida: nada gravado no meio

        await pilot.pause(0.4)
        assert app.temas.fundos_padrao()["signature"].endswith("/signature/backgrounds/b.png")
        assert "● padrão" in _info(app) and "gravando" not in _info(app)
        assert aba.tema_selecionado().fundo_padrao.name == "b.png"
        assert _bg(executor) == [] and not any(c[:3] == ("omarchy", "theme", "set") for c in executor.chamadas)
        assert app.query_one(TabbedContent).active == "temas"  # h/l não trocaram de aba


async def test_um_ou_nenhum_fundo_nao_faz_nada(app):
    async with app.run_test(size=(170, 45)) as pilot:
        await _pronto(app, pilot)
        await _ir(app, pilot, "solo")
        await pilot.press("l", "h", "left", "right")
        await pilot.pause(0.8)
        assert "unico.png" in _info(app) and "1 de 1" in _info(app)
        assert "não tem outro fundo" in str(app.query_one("#temas-status", Label).render())
        await _ir(app, pilot, "vazio")
        await pilot.press("l")
        await pilot.pause()
        assert "não tem fundos" in str(app.query_one("#temas-status", Label).render())
        assert not app.cfg.exists()


async def test_pesquisa_recebe_as_letras(app):
    async with app.run_test(size=(170, 45)) as pilot:
        await _pronto(app, pilot)
        await _ir(app, pilot, "signature")
        await pilot.press("slash")
        await pilot.pause()
        await pilot.press("s", "o", "l", "left", "h")
        await pilot.pause(0.8)
        assert app.query_one("#temas-busca", Input).value == "sohl"
        assert not app.cfg.exists()


@pytest.mark.parametrize("saida", ["outro_tema", "outra_aba", "sair"])
async def test_gravacao_pendente_e_garantida(app, saida):
    async with app.run_test(size=(170, 45)) as pilot:
        await _pronto(app, pilot)
        aba = await _ir(app, pilot, "signature")
        aba.DEBOUNCE_PADRAO = 30  # o timer não chega a disparar
        await pilot.press("l", "l")
        await pilot.pause()
        assert not app.cfg.exists()
        if saida == "outro_tema":
            await pilot.press("j")
        elif saida == "outra_aba":
            await pilot.press("alt+l")
        else:
            await pilot.press("q")
        await pilot.pause()
        assert app.temas.fundos_padrao()["signature"].endswith("c.png")


async def test_previa_ao_vivo_acompanha_o_fundo_e_restaura(app, executor, tmp_path):
    async with app.run_test(size=(170, 45)) as pilot:
        await _pronto(app, pilot)
        aba = await _ir(app, pilot, "signature")
        aba.DEBOUNCE_PADRAO = 0.1
        aba.DEBOUNCE_PREVIA = 0.05
        await pilot.press("v")
        await pilot.pause(0.3)
        await _pronto(app, pilot)
        assert app.previa.ativa and app.previa.aplicado == "signature"
        assert _bg(executor) == []  # sem padrão nem escolha: fica o fundo que o Omarchy pôs
        await pilot.press("l")
        await pilot.pause(0.4)
        await _pronto(app, pilot)
        assert [c[4].rsplit("/", 1)[1] for c in _bg(executor)] == ["b.png"]
        await pilot.press("escape")
        await pilot.pause(0.2)
        await _pronto(app, pilot)
        assert [c[3] for c in executor.chamadas if c[:3] == ("omarchy", "theme", "set")] == ["signature", "solo"]
        assert not app.previa.ativa and app.temas.fundos_padrao()["signature"].endswith("b.png")


async def test_p_abre_a_lista_com_o_padrao_atual(app):
    async with app.run_test(size=(170, 45)) as pilot:
        await _pronto(app, pilot)
        aba = await _ir(app, pilot, "signature")
        aba.DEBOUNCE_PADRAO = 30
        await pilot.press("l")
        await pilot.press("p")  # grava o pendente antes de abrir
        await pilot.pause()
        assert isinstance(app.screen, EscolherFundo)
        assert app.screen.tema.fundo_padrao.name == "b.png"
        await pilot.press("enter")  # primeira opção: sem imagem padrão
        await _pronto(app, pilot)
        assert app.temas.fundos_padrao() == {}
        assert "sem padrão" in _info(app)


def test_atalhos_novos_na_aba_config():
    from omarchy_manager.ui.config import todos_os_atalhos

    teclas = {(onde, tecla): desc for onde, tecla, desc in todos_os_atalhos()}
    assert "Fundo anterior" in teclas[("Temas", "H / ←")]
    assert "Próximo fundo" in teclas[("Temas", "L / →")]
    assert ("Temas", "P") in teclas
