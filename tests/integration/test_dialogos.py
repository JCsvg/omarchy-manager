"""Navegação por setas e hjkl em todos os diálogos, foco inicial seguro e rodapé de teclas."""

from pathlib import Path

import pytest
from textual.app import App
from textual.widgets import Button, Input, OptionList, Static

from omarchy_manager.models import Tema
from omarchy_manager.services.ai_launcher import ADAPTADORES, AiLauncher, IADisponivel
from omarchy_manager.ui.dialogs import Ajuda, Aviso, Confirmacao, Dialogo
from omarchy_manager.ui.share import Compartilhar, Receber
from omarchy_manager.ui.shortcuts import CapturaTecla
from omarchy_manager.ui.themes import SEM_PADRAO, CriarTemaIA, EscolherFundo


class Hospede(App):
    def __init__(self, tmp: Path) -> None:
        super().__init__()
        self.ia = AiLauncher(which=lambda n: None, abrir=lambda *a, **k: None, workspaces=tmp / "ws")
        self.resultado = "nada"

    def abrir(self, dialogo):
        self.push_screen(dialogo, lambda r: setattr(self, "resultado", r))


def _foco(app):
    return getattr(app.focused, "id", None)


def _dica(app):
    return str(app.screen.query(".dica-teclas").first().render())


@pytest.mark.parametrize("ida, volta", [("right", "left"), ("l", "h")])
async def test_confirmacao_move_entre_botoes(tmp_path, ida, volta):
    app = Hospede(tmp_path)
    async with app.run_test(size=(100, 30)) as pilot:
        app.abrir(Confirmacao("Aplicar tema", "Aplicar?", confirmar="Aplicar"))
        await pilot.pause()
        assert _foco(app) == "cancelar"  # foco inicial no lado seguro
        assert "←/→" in _dica(app) and "Esc cancelar" in _dica(app)
        await pilot.press(ida)
        assert _foco(app) == "ok"
        await pilot.press(ida)  # dá a volta
        assert _foco(app) == "cancelar"
        await pilot.press(volta)
        assert _foco(app) == "ok"
        await pilot.press("j")
        assert _foco(app) in ("ok", "cancelar")  # vertical também anda, sem sair do diálogo
        app.screen.query_one("#ok", Button).focus()
        await pilot.press("enter")
        await pilot.pause()
        assert app.resultado is True


async def test_confirmacao_destrutiva_comeca_em_cancelar_e_enter_cancela(tmp_path):
    app = Hospede(tmp_path)
    async with app.run_test(size=(100, 30)) as pilot:
        app.abrir(Confirmacao("Desinstalar", "Remover?", confirmar="Desinstalar", perigo=True))
        await pilot.pause()
        assert _foco(app) == "cancelar"
        await pilot.press("enter")
        await pilot.pause()
        assert app.resultado is False
        app.abrir(Confirmacao("Desinstalar", "Remover?", confirmar="Desinstalar", perigo=True))
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert app.resultado is False


async def test_botao_em_foco_e_o_unico_de_cor_cheia(tmp_path):
    app = Hospede(tmp_path)
    async with app.run_test(size=(100, 30)) as pilot:
        app.abrir(Confirmacao("Aplicar tema", "Aplicar?", confirmar="Aplicar"))
        await pilot.pause()
        cancelar, ok = app.screen.query_one("#cancelar", Button), app.screen.query_one("#ok", Button)
        assert cancelar.has_focus and cancelar.styles.background != ok.styles.background
        fundo_focado = cancelar.styles.background
        await pilot.press("right")
        await pilot.pause()
        assert ok.styles.background == fundo_focado and cancelar.styles.background != fundo_focado


async def test_aviso_e_ajuda(tmp_path):
    app = Hospede(tmp_path)
    async with app.run_test(size=(100, 20)) as pilot:
        app.abrir(Aviso("Atenção", "Texto"))
        await pilot.pause()
        assert _foco(app) == "ok" and "fechar" in _dica(app)
        await pilot.press("h", "l", "j", "k", "left", "down")
        assert isinstance(app.screen, Aviso)
        await pilot.press("enter")
        await pilot.pause()
        assert not isinstance(app.screen, Dialogo)

        app.abrir(Ajuda())
        await pilot.pause()
        caixa = app.screen.query_one("#caixa")
        await pilot.press("j", "j", "down")
        await pilot.pause(0.4)
        assert caixa.scroll_y > 0  # j e seta rolam a ajuda
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, Dialogo)


async def test_lista_de_fundos(tmp_path):
    fundos = tuple(tmp_path / f"{n}.png" for n in "abc")
    tema = Tema("t", "T", tmp_path, True, fundos=fundos)
    app = Hospede(tmp_path)
    async with app.run_test(size=(110, 30)) as pilot:
        app.abrir(EscolherFundo(tema))
        await pilot.pause()
        lista = app.screen.query_one(OptionList)
        assert lista.has_focus and "j/k" in _dica(app)
        await pilot.press("j", "j", "k")
        assert lista.highlighted == 1
        await pilot.press("l")
        assert _foco(app) == "cancelar"
        await pilot.press("k")  # volta para a lista
        assert lista.has_focus
        await pilot.press("enter")
        await pilot.pause()
        assert app.resultado == str(fundos[0])
        app.abrir(EscolherFundo(tema))
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert app.resultado == SEM_PADRAO


async def test_campo_de_texto_recebe_as_letras(tmp_path):
    ias = [IADisponivel(ADAPTADORES[0], "/usr/bin/claude")]
    app = Hospede(tmp_path)
    async with app.run_test(size=(110, 36)) as pilot:
        app.abrir(CriarTemaIA(ias, [], None))
        await pilot.pause()
        nome = app.screen.query_one("#ia-nome", Input)
        assert nome.has_focus
        await pilot.press("h", "j", "k", "l", "left", "right")
        assert nome.value == "hjkl" and nome.has_focus
        await pilot.press("down")  # sai do campo pela seta
        assert not nome.has_focus
        app.screen.query_one("#cancelar", Button).focus()
        await pilot.press("l")
        assert _foco(app) == "ok"
        await pilot.press("h")
        assert _foco(app) == "cancelar"
        await pilot.press("enter")
        await pilot.pause()
        assert app.resultado is None

        app.abrir(Receber())
        await pilot.pause()
        convite = app.screen.query_one("#convite", Input)
        await pilot.press("l", "h")
        assert convite.value == "lh"
        convite.value = ""
        app.screen.query_one("#cancelar", Button).focus()
        await pilot.press("right")
        assert _foco(app) == "procurar"
        await pilot.press("right")
        assert _foco(app) == "conferir"
        await pilot.press("right")  # Baixar e Instalar estão desabilitados: pula e dá a volta
        assert _foco(app) == "cancelar"
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, Dialogo)


async def test_compartilhar(tmp_path):
    pasta = tmp_path / "meu-tema"
    pasta.mkdir()
    (pasta / "colors.toml").write_text('mode = "dark"\n')
    app = Hospede(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        app.abrir(Compartilhar("tema", "meu-tema", "Meu Tema", pasta))
        await pilot.pause()
        assert _foco(app) == "cancelar"
        await pilot.press("l")
        assert _foco(app) == "exportar"
        await pilot.press("right")
        assert _foco(app) == "enviar"
        await pilot.press("h", "h")
        assert _foco(app) == "cancelar"
        await pilot.press("enter")
        await pilot.pause()
        assert not isinstance(app.screen, Dialogo)


def test_todo_dialogo_usa_a_base_comum():
    for classe in (Confirmacao, Aviso, Ajuda, EscolherFundo, CriarTemaIA, Compartilhar, Receber):
        assert issubclass(classe, Dialogo), classe
    # a captura de atalho fica de fora de propósito: ali toda tecla é a resposta
    assert not issubclass(CapturaTecla, Dialogo)


def test_ajuda_e_config_mencionam_os_dialogos():
    from omarchy_manager.ui.config import todos_os_atalhos
    from omarchy_manager.ui.dialogs import TEXTO_AJUDA

    assert "mover entre os botões" in TEXTO_AJUDA
    assert any(onde == "Diálogos" and "botões" in desc for onde, _, desc in todos_os_atalhos())
