"""Aba Compartilhar: IPs, porta verde/vermelha, marcação, aprovação por conexão e recebimento. Rede só em 127.0.0.1."""

import asyncio
import shutil
import socket

import pytest
from textual.coordinate import Coordinate
from textual.widgets import Button, DataTable, Input, Static, TabbedContent
from textual.widgets._footer import FooterKey

from omarchy_manager.app import OmarchyManagerApp
from omarchy_manager.services import caminhos, recebidos
from omarchy_manager.services.hyprland import HyprlandService
from omarchy_manager.services.lan_share import ErroLan
from omarchy_manager.services.oferta import Catalogo, ClienteOferta, ServidorOferta
from omarchy_manager.services.omarchy import OmarchyService
from omarchy_manager.services.plugin_catalog import PluginCatalog
from omarchy_manager.services.previa_ao_vivo import PreviaAoVivo
from omarchy_manager.services.rede import IpLocal
from omarchy_manager.services.temas import ThemeService
from omarchy_manager.ui import compartilhar
from omarchy_manager.ui.compartilhar import AbaCompartilhar, ListaRemota
from omarchy_manager.ui.compartilhar import PedirCaminho
from omarchy_manager.ui.navegacao import AjudaAba
from omarchy_manager.ui.dialogs import Aviso, Confirmacao

pytestmark = pytest.mark.skipif(shutil.which("openssl") is None, reason="openssl ausente")


@pytest.fixture
def app(tmp_path, executor, fixtures, monkeypatch):
    monkeypatch.setattr(caminhos, "PROIBIDOS", (tmp_path / "proibido",))
    monkeypatch.setattr(caminhos, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(caminhos, "BACKUPS_DIR", tmp_path / "bk")
    monkeypatch.setattr(recebidos, "pasta_downloads", lambda: tmp_path / "downloads")
    monkeypatch.setattr(compartilhar.rede, "ips_locais", lambda: [IpLocal("wlan0", "127.0.0.1", "Wi-Fi")])
    monkeypatch.delenv("HYPRLAND_INSTANCE_SIGNATURE", raising=False)
    sistema = tmp_path / "sistema"
    (sistema / "signature").mkdir(parents=True)
    (sistema / "signature" / "colors.toml").write_text((fixtures / "colors_dark.toml").read_text())
    usuario = tmp_path / "t-u"
    (usuario / "meu-tema").mkdir(parents=True)
    (usuario / "meu-tema" / "colors.toml").write_text((fixtures / "colors_dark.toml").read_text())
    estado = tmp_path / "estado"
    estado.mkdir()
    (estado / "theme.name").write_text("signature\n")
    monkeypatch.setattr(caminhos, "OMARCHY_STATE_CURRENT", estado)
    executor.responder(["omarchy", "plugin", "list", "--json"], "[]")
    executor.responder(["hyprctl", "binds", "-j"], "[]")
    executor.responder(["omarchy", "theme", "list"], "Meu Tema\nSignature\n")
    omarchy = OmarchyService(executor)
    return OmarchyManagerApp(
        omarchy=omarchy,
        hyprland=HyprlandService(executor),
        catalogo=PluginCatalog(executor, raiz_usuario=tmp_path / "p-u", raiz_sistema=tmp_path / "p-s", traducoes={}),
        temas=ThemeService(omarchy, raiz_usuario=usuario, raiz_sistema=sistema, raiz_fundos_usuario=tmp_path / "t-f", arquivo_config=tmp_path / "cfg.toml"),
        previa=PreviaAoVivo(omarchy, tmp_path / "st" / "previa-original.json"),
        aba_inicial="compartilhar",
    )


async def _pronto(app, pilot):
    for _ in range(3):
        await pilot.pause()
        await app.workers.wait_for_complete()
    await pilot.pause()


async def _esperar_tela(app, pilot, tipo, tentativas=100):
    for _ in range(tentativas):
        if isinstance(app.screen, tipo):
            return app.screen
        await pilot.pause(0.05)
    raise AssertionError(f"tela {tipo.__name__} não apareceu; há {type(app.screen).__name__}")


def _texto(tela):
    return "\n".join(str(w.render()) for w in tela.query(Static))


def _porta_livre():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    n = s.getsockname()[1]
    s.close()
    return n


async def test_tecla_7_ips_e_nenhum_item_marcado(app):
    async with app.run_test(size=(150, 60)) as pilot:
        await _pronto(app, pilot)
        await pilot.press("1")
        await pilot.press("7")
        await _pronto(app, pilot)
        assert app.query_one(TabbedContent).active == "compartilhar"
        aba = app.query_one(AbaCompartilhar)
        assert aba.query_one("#comp-ips", DataTable).get_row_at(0) == ["wlan0", "Wi-Fi", "127.0.0.1"]
        itens = aba.query_one("#comp-itens", DataTable)
        assert itens.row_count == 1 and itens.get_row_at(0)[1:3] == ["tema", "Meu Tema"] and itens.get_row_at(0)[0].plain == "[ ]"  # só tema do usuário
        assert aba.catalogo.itens() == []  # nada exposto por padrão
        await pilot.click("#comp-oferecer")
        await _pronto(app, pilot)
        assert aba.servidor is None and "Marque ao menos 1" in str(aba.query_one("#comp-status", Static).render())


async def test_porta_verde_vermelha(app):
    ocupada = socket.socket()
    ocupada.bind(("127.0.0.1", 0))
    ocupada.listen(1)
    porta_ocupada = ocupada.getsockname()[1]
    try:
        async with app.run_test(size=(150, 60)) as pilot:
            await _pronto(app, pilot)
            campo = app.query_one("#comp-porta", Input)
            campo.value = str(_porta_livre())
            await _pronto(app, pilot)
            assert campo.has_class("livre") and not campo.has_class("ocupada")
            campo.value = str(porta_ocupada)
            await _pronto(app, pilot)
            assert campo.has_class("ocupada") and not campo.has_class("livre")
            assert "ocupada" in str(app.query_one("#comp-porta-estado", Static).render())
            campo.value = "70000"
            await _pronto(app, pilot)
            assert campo.has_class("ocupada")
            campo.value = ""
            await _pronto(app, pilot)
            assert campo.has_class("ocupada")
    finally:
        ocupada.close()


async def test_adicionar_pasta_e_arquivo_sensivel(app, tmp_path):
    pasta = tmp_path / "minha-pasta"
    pasta.mkdir()
    (pasta / "x.txt").write_text("x")
    (tmp_path / "meu-token.txt").write_text("t")
    async with app.run_test(size=(150, 60)) as pilot:
        await _pronto(app, pilot)
        aba = app.query_one(AbaCompartilhar)
        await pilot.click("#comp-pasta")
        d = await _esperar_tela(app, pilot, PedirCaminho)
        d.query_one(Input).value = str(pasta)
        await pilot.press("enter")
        await _pronto(app, pilot)
        tabela = aba.query_one("#comp-itens", DataTable)
        assert tabela.row_count == 2 and tabela.get_row_at(1)[1:3] == ["pasta", "minha-pasta"]
        tabela.focus()
        tabela.move_cursor(row=1)
        await pilot.press("space")
        assert [i.tipo for i in aba.catalogo.itens()] == ["pasta"]
        await pilot.press("space")  # desmarca
        assert aba.catalogo.itens() == []
        await pilot.click("#comp-arquivo")
        d = await _esperar_tela(app, pilot, PedirCaminho)
        d.query_one(Input).value = str(tmp_path / "meu-token.txt")
        await pilot.press("enter")
        await _esperar_tela(app, pilot, Aviso)  # recusado pela regra de exclusão do bundle
        await pilot.press("enter")
        await _pronto(app, pilot)
        assert tabela.row_count == 2 and aba.catalogo.itens() == []


async def test_enter_marca_e_desmarca_item(app, tmp_path):
    pasta = tmp_path / "minha-pasta"
    pasta.mkdir()
    (pasta / "x.txt").write_text("x")
    async with app.run_test(size=(150, 60)) as pilot:
        await _pronto(app, pilot)
        aba = app.query_one(AbaCompartilhar)
        await pilot.click("#comp-pasta")
        d = await _esperar_tela(app, pilot, PedirCaminho)
        d.query_one(Input).value = str(pasta)
        await pilot.press("enter")
        await _pronto(app, pilot)
        tabela = aba.query_one("#comp-itens", DataTable)
        tabela.focus()
        tabela.move_cursor(row=1)
        await pilot.press("enter")
        assert tabela.get_cell_at(Coordinate(1, 0)).plain == "[x]"
        assert [i.tipo for i in aba.catalogo.itens()] == ["pasta"]
        await pilot.press("enter")
        assert tabela.get_cell_at(Coordinate(1, 0)).plain == "[ ]"
        assert aba.catalogo.itens() == []


async def test_oferecer_exige_aprovacao_por_conexao(app, tmp_path):
    async with app.run_test(size=(150, 60)) as pilot:
        await _pronto(app, pilot)
        aba = app.query_one(AbaCompartilhar)
        aba.query_one("#comp-itens", DataTable).focus()
        await pilot.press("space")
        aba.query_one("#comp-porta", Input).value = str(_porta_livre())
        await _pronto(app, pilot)
        await pilot.click("#comp-oferecer")
        for _ in range(100):
            if aba.servidor is not None:
                break
            await pilot.pause(0.05)
        srv = aba.servidor
        assert srv is not None and "Código" in str(aba.query_one("#comp-oferta-info", Static).render())
        assert srv.codigo in str(aba.query_one("#comp-oferta-info", Static).render())

        cli = ClienteOferta("127.0.0.1", srv.porta)
        assert await asyncio.to_thread(cli.sondar) == srv.codigo

        # recusa: o cliente vê 403 e nada é listado
        t = asyncio.create_task(asyncio.to_thread(cli.autorizar))
        tela = await _esperar_tela(app, pilot, Confirmacao)
        assert "127.0.0.1" in _texto(tela)
        await pilot.press("enter")  # foco começa em Cancelar
        with pytest.raises(ErroLan, match="recusou"):
            await t
        with pytest.raises(ErroLan, match="403"):
            await asyncio.to_thread(cli.listar)

        # aprova: Cancelar -> Aprovar
        t = asyncio.create_task(asyncio.to_thread(cli.autorizar))
        await _esperar_tela(app, pilot, Confirmacao)
        await pilot.press("right", "enter")
        await t
        itens = await asyncio.to_thread(cli.listar)
        assert [(i["tipo"], i["nome"]) for i in itens] == [("tema", "Meu Tema")]
        arq, meta = await asyncio.to_thread(cli.baixar, itens[0]["id"], tmp_path / "dl")
        assert meta["tipo"] == "tema" and arq.stat().st_size > 0

        await pilot.click("#comp-oferecer")  # parar
        await _pronto(app, pilot)
        assert aba.servidor is None
        with pytest.raises(ErroLan):
            await asyncio.to_thread(ClienteOferta("127.0.0.1", srv.porta, timeout=3).sondar)


async def test_receber_arquivo_da_outra_pessoa(app, tmp_path):
    origem = tmp_path / "oferecido" / "nota.txt"
    origem.parent.mkdir()
    origem.write_text("conteudo")
    cat = Catalogo()
    cat.adicionar_arquivo(origem)
    srv = ServidorOferta(cat, lambda ip, codigo: True, "127.0.0.1", 0)
    srv.iniciar()
    try:
        async with app.run_test(size=(150, 60)) as pilot:
            await _pronto(app, pilot)
            aba = app.query_one(AbaCompartilhar)
            aba.query_one("#comp-dest-ip", Input).value = "127.0.0.1"
            aba.query_one("#comp-dest-porta", Input).value = str(srv.porta)
            await pilot.click("#comp-receber")
            tela = await _esperar_tela(app, pilot, Confirmacao)
            assert srv.codigo in _texto(tela)
            await pilot.press("right", "enter")
            lista = await _esperar_tela(app, pilot, ListaRemota)
            await pilot.press("space", "right", "right", "enter")  # marca e baixa
            for _ in range(100):
                await pilot.pause(0.05)
                if (tmp_path / "downloads" / "nota.txt").exists():
                    break
            destino = tmp_path / "downloads" / "nota.txt"
            assert destino.read_text() == "conteudo" and not destino.stat().st_mode & 0o111

            # mesma coisa de novo: já existe, pergunta; Cancelar mantém o arquivo
            destino.write_text("meu, nao sobrescreva")
            await pilot.click("#comp-receber")
            await _esperar_tela(app, pilot, Confirmacao)
            await pilot.press("right", "enter")
            await _esperar_tela(app, pilot, ListaRemota)
            await pilot.press("space", "right", "right", "enter")
            conf = await _esperar_tela(app, pilot, Confirmacao)
            assert "Sobrescrever" in _texto(conf)
            await pilot.press("enter")  # foco começa em Cancelar
            await _pronto(app, pilot)
            assert destino.read_text() == "meu, nao sobrescreva"
    finally:
        srv.encerrar()


async def test_receber_sem_ip_avisa(app):
    async with app.run_test(size=(150, 60)) as pilot:
        await _pronto(app, pilot)
        await pilot.click("#comp-receber")
        await _pronto(app, pilot)
        assert "Digite o IP" in str(app.query_one("#comp-status", Static).render())


async def test_tema_recebido_passa_pela_revisao_e_nao_e_aplicado(app, tmp_path, fixtures, monkeypatch, executor):
    from omarchy_manager.ui.share import RevisarBundle

    monkeypatch.setattr(caminhos, "OMARCHY_USER_THEMES", tmp_path / "instalados")
    tema = tmp_path / "oferecido" / "tema-novo"
    tema.mkdir(parents=True)
    (tema / "colors.toml").write_text((fixtures / "colors_dark.toml").read_text())
    cat = Catalogo()
    cat.adicionar_tema("tema-novo", "Tema Novo", tema)
    srv = ServidorOferta(cat, lambda ip, codigo: True, "127.0.0.1", 0)
    srv.iniciar()
    try:
        async with app.run_test(size=(150, 60)) as pilot:
            await _pronto(app, pilot)
            aba = app.query_one(AbaCompartilhar)
            aba.query_one("#comp-dest-ip", Input).value = "127.0.0.1"
            aba.query_one("#comp-dest-porta", Input).value = str(srv.porta)
            await pilot.click("#comp-receber")
            await _esperar_tela(app, pilot, Confirmacao)
            await pilot.press("right", "enter")
            await _esperar_tela(app, pilot, ListaRemota)
            await pilot.press("space", "right", "right", "enter")
            rev = await _esperar_tela(app, pilot, RevisarBundle)
            assert "NÃO será aplicado" in _texto(rev)
            assert not (tmp_path / "instalados" / "tema-novo").exists()  # nada instalado antes do sim
            await pilot.press("right", "enter")  # Cancelar -> Instalar desligado
            for _ in range(60):
                await pilot.pause(0.05)
                if (tmp_path / "instalados" / "tema-novo" / "colors.toml").exists():
                    break
            assert (tmp_path / "instalados" / "tema-novo" / "colors.toml").exists()
            assert not any("set" in c for c in executor.chamadas if c[:2] == ("omarchy", "theme"))
    finally:
        srv.encerrar()


# ------------------------------------------------------------ navegação por seções, botões, ajuda e rodapé

def _foco(app):
    return app.focused.id if app.focused is not None else None


@pytest.mark.parametrize("descer,subir", [("ctrl+down", "ctrl+up"), ("ctrl+j", "ctrl+k")])
async def test_secao_seguinte_e_anterior(app, descer, subir):
    async with app.run_test(size=(120, 50)) as pilot:
        await _pronto(app, pilot)
        assert _foco(app) == "comp-itens"  # foco inicial: a lista do que oferecer
        await pilot.press(subir)
        assert _foco(app) == "comp-porta"
        await pilot.press(subir)
        assert _foco(app) == "comp-ips"
        await pilot.press(descer)
        assert _foco(app) == "comp-porta"
        await pilot.press(descer)
        assert _foco(app) == "comp-itens"
        await pilot.press(descer)
        assert _foco(app) == "comp-dest-ip"
        await pilot.press(descer)
        assert _foco(app) == "comp-dest-ip"  # sem dar a volta


async def test_ctrl_jk_dentro_do_campo_nao_digita(app):
    async with app.run_test(size=(120, 50)) as pilot:
        await _pronto(app, pilot)
        await pilot.press("ctrl+k")
        assert _foco(app) == "comp-porta"
        await pilot.press("ctrl+j")
        assert _foco(app) == "comp-itens"
        assert app.query_one("#comp-porta", Input).value == "8765"


async def test_botoes_com_ctrl_setas_e_hl(app):
    async with app.run_test(size=(120, 50)) as pilot:
        await _pronto(app, pilot)
        await pilot.press("ctrl+right")
        assert _foco(app) == "comp-pasta"
        await pilot.press("ctrl+l")
        assert _foco(app) == "comp-arquivo"
        await pilot.press("ctrl+h")
        assert _foco(app) == "comp-pasta"
        await pilot.press("ctrl+left")
        assert _foco(app) == "comp-oferecer"  # dá a volta
        await pilot.press("ctrl+enter")  # sem item marcado: só avisa
        await _pronto(app, pilot)
        assert "Marque ao menos 1 item" in str(app.query_one("#comp-status", Static).render())


@pytest.mark.parametrize("tecla", ["ctrl+@", "ctrl+space"])
async def test_ajuda_abre_e_fecha(app, tecla):
    async with app.run_test(size=(120, 50)) as pilot:
        await _pronto(app, pilot)
        await pilot.press(tecla)
        await pilot.pause()
        assert isinstance(app.screen, AjudaAba)
        await pilot.press(tecla)
        await pilot.pause()
        assert not isinstance(app.screen, AjudaAba)
        for fecha in ("escape", "q"):
            await pilot.press(tecla)
            await pilot.pause()
            assert isinstance(app.screen, AjudaAba)
            await pilot.press(fecha)
            await pilot.pause()
            assert not isinstance(app.screen, AjudaAba)
        assert app.is_running  # q fechou o painel, não o app


async def test_rodape_enxuto(app):
    async with app.run_test(size=(120, 50)) as pilot:
        await _pronto(app, pilot)
        await pilot.pause()
        teclas = [str(k.key_display) if hasattr(k, "key_display") else k.key for k in app.query(FooterKey)]
        assert 1 <= len(teclas) <= 6
        assert "space" in [k.key for k in app.query(FooterKey)] or "Espaço" in teclas or len(teclas) >= 3
        await pilot.press("ctrl+k", "ctrl+k")  # lista de IPs
        await pilot.pause()
        assert len(list(app.query(FooterKey))) <= 3
