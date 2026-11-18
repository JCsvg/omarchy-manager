"""Aba Webapps e a opção da aba Config: por teclado e por mouse. Tudo em diretórios temporários."""

import json
import os
from pathlib import Path

import pytest
from textual.widgets import Button, Checkbox, DataTable, Input, OptionList, Select, Static, TabbedContent

from omarchy_manager.app import OmarchyManagerApp
from omarchy_manager.services import caminhos
from omarchy_manager.services import webapps as w
from omarchy_manager.services.hyprland import HyprlandService
from omarchy_manager.services.omarchy import OmarchyService
from omarchy_manager.services.plugin_catalog import PluginCatalog
from omarchy_manager.services.previa_ao_vivo import PreviaAoVivo
from omarchy_manager.services.temas import ThemeService
from omarchy_manager.ui.dialogs import Confirmacao
from omarchy_manager.ui.webapps import AbaWebapps, AdicionarWebapp, EscolherConta

APPS = {"Agenda": "https://calendar.google.com/", "Docs": "https://docs.google.com/document/", "Drive": "https://drive.google.com/", "Mapas": "https://maps.google.com/"}


def _montar(tmp_path, executor, monkeypatch, chrome=True, aba_inicial="webapps", wrapper=True):
    monkeypatch.setattr(caminhos, "PROIBIDOS", (tmp_path / "proibido",))
    monkeypatch.delenv("HYPRLAND_INSTANCE_SIGNATURE", raising=False)
    if chrome:
        monkeypatch.setenv(w.ENV_NAVEGADOR, "google-chrome.desktop")
    pasta = Path(os.environ[w.ENV_CHROME])
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "Local State").write_text(json.dumps({"profile": {"info_cache": {
        "Default": {"name": "Pessoal", "user_name": "pessoal@exemplo.com"},
        "Profile 1": {"name": "Trabalho", "user_name": "trabalho@exemplo.com"},
        "Profile 2": {"name": "Sem login", "user_name": ""},
    }}}))
    apps = Path(os.environ[w.ENV_APPS])
    apps.mkdir(parents=True, exist_ok=True)
    for nome, url in APPS.items():
        (apps / f"{nome}.desktop").write_text(w.texto_desktop(nome, url))
    Path(os.environ[w.ENV_PERFIS]).write_text("# meus perfis\ndocs.google.com = Profile 1\n")
    bin_ = Path(os.environ[w.ENV_BIN])
    bin_.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("PATH", f"{bin_}:{os.environ['PATH']}")
    if wrapper:
        (bin_ / w.COMANDO).write_text(w.wrapper_empacotado().read_text())
        (bin_ / w.COMANDO).chmod(0o755)
    sistema = tmp_path / "sistema" / "signature"
    sistema.mkdir(parents=True)
    (sistema / "colors.toml").write_text(Path(__file__).parent.parent.joinpath("fixtures/colors_dark.toml").read_text())
    estado = tmp_path / "estado"
    estado.mkdir()
    (estado / "theme.name").write_text("signature\n")
    monkeypatch.setattr(caminhos, "OMARCHY_STATE_CURRENT", estado)
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


@pytest.fixture
def app(tmp_path, executor, monkeypatch):
    return _montar(tmp_path, executor, monkeypatch)


async def _pronto(app, pilot):
    for _ in range(3):
        await pilot.pause()
        await app.workers.wait_for_complete()
    await pilot.pause()


def _perfis():
    return w.Perfis.ler()


def _tabela(app):
    return app.query_one("#wa-tabela", DataTable)


def _celula(app, linha, col):
    return str(_tabela(app).get_row_at(linha)[col])


async def test_lista_com_contas_e_padrao(app):
    async with app.run_test(size=(170, 45)) as pilot:
        await _pronto(app, pilot)
        assert _tabela(app).row_count == 4
        assert app.focused is _tabela(app)  # foco inicial na lista
        assert _celula(app, 1, 0) == "Docs" and _celula(app, 1, 2) == "Trabalho (trabalho@exemplo.com)"
        assert _celula(app, 0, 2) == "padrão do Chrome"
        assert "nenhuma" in str(app.query_one("#wa-padrao", Static).render())


async def test_teclado_escolher_conta_sem_conta_e_padrao(app):
    async with app.run_test(size=(170, 45)) as pilot:
        await _pronto(app, pilot)
        await pilot.press("c")  # Agenda
        await _pronto(app, pilot)
        assert isinstance(app.screen, EscolherConta)
        opcoes = app.screen.query_one("#contas", OptionList)
        assert opcoes.option_count == 3  # nenhuma + 2 logadas (a sem login não entra)
        await pilot.press("j", "j", "enter")  # Trabalho
        await _pronto(app, pilot)
        assert _perfis().mapa()["calendar.google.com"] == "Profile 1"
        assert _celula(app, 0, 2) == "Trabalho (trabalho@exemplo.com)"
        await pilot.press("s")
        await _pronto(app, pilot)
        assert "calendar.google.com" not in _perfis().mapa()
        assert "# meus perfis" in Path(os.environ[w.ENV_PERFIS]).read_text()  # comentário preservado
        await pilot.press("d", "j", "enter")  # conta padrão: Pessoal
        await _pronto(app, pilot)
        assert _perfis().padrao() == "Default"
        assert _celula(app, 0, 2) == "conta padrão"
        assert "Pessoal (pessoal@exemplo.com)" in str(app.query_one("#wa-padrao", Static).render())


async def test_mouse_escolher_conta_com_clique(app):
    async with app.run_test(size=(170, 45)) as pilot:
        await _pronto(app, pilot)
        await pilot.click("#wa-tabela", offset=(4, 2))  # linha 1 (Docs): o cabeçalho ocupa a linha 0
        await pilot.pause()
        assert _tabela(app).cursor_row == 1
        await pilot.click("#wa-conta")
        await _pronto(app, pilot)
        assert isinstance(app.screen, EscolherConta)
        await pilot.click("#contas", offset=(5, 1))  # primeira opção: sem conta específica
        await _pronto(app, pilot)
        assert not isinstance(app.screen, EscolherConta)  # o clique confirma sem Enter
        assert "docs.google.com" not in _perfis().mapa()


async def test_mouse_botoes_sem_conta_padrao_e_cancelar(app):
    async with app.run_test(size=(170, 45)) as pilot:
        await _pronto(app, pilot)
        _tabela(app).move_cursor(row=1)  # Docs, com Profile 1
        await pilot.click("#wa-sem")
        await _pronto(app, pilot)
        assert "docs.google.com" not in _perfis().mapa()
        await pilot.click("#wa-padrao-btn")
        await _pronto(app, pilot)
        assert isinstance(app.screen, EscolherConta)
        await pilot.click("#contas", offset=(5, 3))  # segunda conta (Trabalho)
        await _pronto(app, pilot)
        assert _perfis().padrao() == "Profile 1"
        await pilot.click("#wa-padrao-btn")
        await _pronto(app, pilot)
        await pilot.click("#cancelar")
        await _pronto(app, pilot)
        assert _perfis().padrao() == "Profile 1"


async def test_adicionar_so_com_teclado(app):
    async with app.run_test(size=(170, 45)) as pilot:
        await _pronto(app, pilot)
        await pilot.press("a")
        await _pronto(app, pilot)
        assert isinstance(app.screen, AdicionarWebapp)
        await pilot.press("enter")  # nome vazio
        assert "nome" in str(app.screen.query_one("#wa-erro", Static).render()).lower()
        await pilot.press(*"Contatos")
        await pilot.press("ctrl+j", *"https://contacts.google.com", "ctrl+j")
        await pilot.press("enter")  # abre o Select
        await pilot.press("down", "down", "enter")  # Trabalho
        await pilot.press("ctrl+j", "ctrl+l", "ctrl+enter")  # botões: Cancelar, Adicionar
        await _pronto(app, pilot)
        assert _tabela(app).row_count == 5
        assert (Path(os.environ[w.ENV_APPS]) / "Contatos.desktop").exists()
        assert _perfis().mapa()["contacts.google.com"] == "Profile 1"


async def test_adicionar_so_com_mouse_sem_conta_e_validacao(app):
    async with app.run_test(size=(170, 45)) as pilot:
        await _pronto(app, pilot)
        await pilot.click("#wa-adicionar")
        await _pronto(app, pilot)
        assert isinstance(app.screen, AdicionarWebapp)
        await pilot.click("#wa-nome")
        await pilot.press(*"Docs")  # duplicado
        await pilot.click("#wa-link")
        await pilot.press(*"https://x.com")
        await pilot.click("#ok")
        await pilot.pause()
        assert "Já existe" in str(app.screen.query_one("#wa-erro", Static).render())
        app.screen.query_one("#wa-nome", Input).value = "Contatos"
        app.screen.query_one("#wa-link", Input).value = "javascript:alert(1)"
        await pilot.pause(0.4)  # o Button ignora um segundo clique em 0,2 s
        await pilot.click("#ok")
        await pilot.pause()
        assert "http" in str(app.screen.query_one("#wa-erro", Static).render())
        app.screen.query_one("#wa-link", Input).value = "contacts.google.com"
        await pilot.pause(0.4)
        await pilot.click("#ok")  # sem escolher conta: nada no perfis.conf
        await _pronto(app, pilot)
        assert _tabela(app).row_count == 5
        assert "contacts.google.com" not in _perfis().mapa()
        await pilot.click("#wa-adicionar")
        await _pronto(app, pilot)
        await pilot.click("#cancelar")
        await _pronto(app, pilot)
        assert _tabela(app).row_count == 5


async def test_mouse_escolher_conta_no_dialogo_de_adicionar(app):
    async with app.run_test(size=(170, 45)) as pilot:
        await _pronto(app, pilot)
        await pilot.click("#wa-adicionar")
        await _pronto(app, pilot)
        app.screen.query_one("#wa-nome", Input).value = "Contatos"
        app.screen.query_one("#wa-link", Input).value = "https://contacts.google.com"
        await pilot.click("#wa-conta")  # abre a lista do Select
        await pilot.pause()
        await pilot.click("SelectOverlay", offset=(4, 3))  # Trabalho
        await pilot.pause()
        assert app.screen.query_one("#wa-conta", Select).value == "Profile 1"
        await pilot.click("#ok")
        await _pronto(app, pilot)
        assert _perfis().mapa()["contacts.google.com"] == "Profile 1"


async def test_remover_com_confirmacao_por_clique(app):
    async with app.run_test(size=(170, 45)) as pilot:
        await _pronto(app, pilot)
        await pilot.click("#wa-remover")
        await _pronto(app, pilot)
        assert isinstance(app.screen, Confirmacao)
        await pilot.click("#ok")
        await _pronto(app, pilot)
        assert _tabela(app).row_count == 3
        assert not (Path(os.environ[w.ENV_APPS]) / "Agenda.desktop").exists()


async def test_instalar_wrapper_ausente_com_confirmacao(tmp_path, executor, monkeypatch):
    app = _montar(tmp_path, executor, monkeypatch, wrapper=False)
    async with app.run_test(size=(170, 45)) as pilot:
        await _pronto(app, pilot)
        botao = app.query_one("#wa-instalar", Button)
        assert botao.display and "wrapper" in str(app.query_one("#wa-wrapper", Static).render())
        await pilot.click("#wa-instalar")
        await _pronto(app, pilot)
        assert isinstance(app.screen, Confirmacao)
        alvo = w.wrapper_alvo()
        assert not alvo.exists()  # só instala depois do sim
        await pilot.click("#ok")
        await _pronto(app, pilot)
        assert alvo.read_text() == w.wrapper_empacotado().read_text() and os.access(alvo, os.X_OK)
        assert not app.query_one("#wa-instalar", Button).display


async def test_instalar_wrapper_cancelado_nao_grava(tmp_path, executor, monkeypatch):
    app = _montar(tmp_path, executor, monkeypatch, wrapper=False)
    async with app.run_test(size=(170, 45)) as pilot:
        await _pronto(app, pilot)
        await pilot.press("i")
        await _pronto(app, pilot)
        await pilot.press("enter")  # foco começa em Cancelar
        await _pronto(app, pilot)
        assert not w.wrapper_alvo().exists()


async def test_aba_oculta_por_padrao_sem_chrome_e_8_nao_abre(tmp_path, executor, monkeypatch):
    app = _montar(tmp_path, executor, monkeypatch, chrome=False, aba_inicial="plugins")
    async with app.run_test(size=(170, 45)) as pilot:
        await _pronto(app, pilot)
        abas = app.query_one(TabbedContent)
        assert not app.webapps_ativa and not abas.get_tab("webapps").display
        await pilot.press("8")
        await _pronto(app, pilot)
        assert abas.active == "plugins"
        for _ in range(8):  # Alt+L dá a volta sem passar pela aba oculta
            await pilot.press("alt+l")
            await _pronto(app, pilot)
            assert abas.active != "webapps"


async def test_aba_visivel_com_chrome_e_teclas_continuam_coerentes(tmp_path, executor, monkeypatch):
    app = _montar(tmp_path, executor, monkeypatch, aba_inicial="plugins")
    async with app.run_test(size=(170, 45)) as pilot:
        await _pronto(app, pilot)
        abas = app.query_one(TabbedContent)
        assert app.webapps_ativa and abas.get_tab("webapps").display
        await pilot.press("7")
        await _pronto(app, pilot)
        assert abas.active == "compartilhar"
        await pilot.press("8")
        await _pronto(app, pilot)
        assert abas.active == "webapps"
        await pilot.press("alt+l")
        await _pronto(app, pilot)
        assert abas.active == "atalhos"


async def test_config_liga_e_desliga_por_clique_e_persiste(tmp_path, executor, monkeypatch):
    app = _montar(tmp_path, executor, monkeypatch, chrome=False, aba_inicial="config")
    async with app.run_test(size=(170, 45)) as pilot:
        await _pronto(app, pilot)
        abas = app.query_one(TabbedContent)
        assert not abas.get_tab("webapps").display
        await pilot.click("#config-webapps")
        await _pronto(app, pilot)
        assert app.webapps_ativa and abas.get_tab("webapps").display
        assert w.aba_ativa("firefox.desktop") is True  # gravado em config.toml (tmp)
        await pilot.press("8")
        await _pronto(app, pilot)
        assert abas.active == "webapps"
        app.action_aba("config")
        await _pronto(app, pilot)
        await pilot.click("#config-webapps")
        await _pronto(app, pilot)
        assert not app.webapps_ativa and not abas.get_tab("webapps").display
        assert w.aba_ativa("google-chrome.desktop") is False


async def test_config_liga_por_teclado(tmp_path, executor, monkeypatch):
    app = _montar(tmp_path, executor, monkeypatch, chrome=False, aba_inicial="config")
    async with app.run_test(size=(170, 45)) as pilot:
        await _pronto(app, pilot)
        await pilot.press("ctrl+j")
        assert app.focused.id == "config-webapps"
        await pilot.press("space")
        await _pronto(app, pilot)
        assert app.webapps_ativa


async def test_desativar_com_a_aba_aberta_volta_para_config(app):
    async with app.run_test(size=(170, 45)) as pilot:
        await _pronto(app, pilot)
        app.aplicar_aba_webapps(False)
        await _pronto(app, pilot)
        assert app.query_one(TabbedContent).active == "config"


async def test_aba_clicavel_na_barra_e_ajuda(app):
    async with app.run_test(size=(170, 45)) as pilot:
        await _pronto(app, pilot)
        await pilot.press("f1")
        await _pronto(app, pilot)
        assert "escolher a conta" in "\n".join(str(s.render()) for s in app.screen.query(Static))


# Auditoria de mouse nas outras abas

async def test_rodape_e_clicavel(app):
    from textual.widgets._footer import FooterKey

    async with app.run_test(size=(170, 45)) as pilot:
        await _pronto(app, pilot)
        chaves = list(app.query(FooterKey))
        assert chaves, "rodapé sem teclas"
        alvo = next(k for k in chaves if k.action == "adicionar")
        await pilot.click(alvo)
        await _pronto(app, pilot)
        assert isinstance(app.screen, AdicionarWebapp)  # clicar na tecla do rodapé executa a ação
        await pilot.click("#cancelar")
        await _pronto(app, pilot)
        ajuda = next(k for k in app.query(FooterKey) if k.action == "ajuda_aba")
        await pilot.click(ajuda)
        await _pronto(app, pilot)
        from omarchy_manager.ui.navegacao import AjudaAba
        assert isinstance(app.screen, AjudaAba)


async def test_temas_botoes_de_fundo_e_previa_por_clique(app):
    async with app.run_test(size=(170, 45)) as pilot:
        app.action_aba("temas")
        await _pronto(app, pilot)
        from omarchy_manager.ui.themes import AbaTemas

        aba = app.query_one(AbaTemas)
        chamadas = []
        aba.action_fundo_relativo = lambda p: chamadas.append(("fundo", p))
        aba.action_alternar_previa = lambda: chamadas.append("previa")
        aba.action_aplicar_fundo = lambda: chamadas.append("so_fundo")
        for id_ in ("btn-fundo-prox", "btn-fundo-ant", "btn-so-fundo", "btn-previa"):
            await pilot.click(f"#{id_}")
            await pilot.pause(0.3)
        assert chamadas == [("fundo", 1), ("fundo", -1), "so_fundo", "previa"]


async def test_compartilhar_marcar_por_botao(app, tmp_path):
    from omarchy_manager.ui.compartilhar import AbaCompartilhar

    async with app.run_test(size=(170, 60)) as pilot:
        app.action_aba("compartilhar")
        await _pronto(app, pilot)
        aba = app.query_one(AbaCompartilhar)
        marcados = []
        aba._marcar_linha = lambda: marcados.append(1)
        await pilot.click("#comp-marcar")
        assert marcados == [1]  # o botão não depende de o foco estar na tabela


async def test_lista_remota_marcar_por_botao_e_clique_na_linha():
    from omarchy_manager.ui.compartilhar import ListaRemota

    itens = [{"id": "a", "tipo": "pasta", "nome": "x", "tamanho": 10}, {"id": "b", "tipo": "arquivo", "nome": "y", "tamanho": 20}]
    from textual.app import App

    class Hospedeiro(App):
        resultado = "pendente"

        def on_mount(self):
            self.push_screen(ListaRemota(itens, "ip"), lambda r: setattr(self, "resultado", r))

    h = Hospedeiro()
    async with h.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.click("#marcar")
        await pilot.pause(0.3)
        await pilot.click("#ok")
        await pilot.pause()
        assert h.resultado == ["a"]
