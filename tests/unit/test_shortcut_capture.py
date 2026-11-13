from pathlib import Path

from omarchy_manager.services.hyprland import HyprlandService
from omarchy_manager.services.shortcut_capture import (
    SUBMAP,
    TECLAS_CAPTURA,
    CapturaHyprland,
    combinacao_de_tecla_textual,
    gerar_lua_definicao,
    gerar_lua_entrar,
    gerar_lua_sair,
    interpretar_resultado,
)


def test_lua_definicao_cobre_as_teclas():
    lua = gerar_lua_definicao(Path("/run/user/1000/x.txt"))
    assert "/run/user/1000/x.txt" in lua and SUBMAP in lua
    for t in ("Q", "code:59", "code:94", "F24", "XF86AudioMute", "PRINT"):
        assert f'"{t}"' in lua
    assert lua.count("hl.define_submap") == 1
    assert "_G.omgr_capture_defined" in lua
    assert len(set(TECLAS_CAPTURA)) == len(TECLAS_CAPTURA)


def test_lua_escapa_caminho_com_aspas():
    lua = gerar_lua_definicao(Path('/tmp/a"b'))
    assert '"/tmp/a\\"b"' in lua


def test_entrar_e_sair():
    assert gerar_lua_entrar() == f'hl.dispatch(hl.dsp.submap("{SUBMAP}"))'
    assert gerar_lua_sair() == 'hl.dispatch(hl.dsp.submap("reset"))'


def test_interpretar_resultado():
    assert interpretar_resultado("SUPER + SHIFT + Q\n").canonica == "SUPER + SHIFT + Q"
    assert interpretar_resultado("SUPER + code:59").canonica == "SUPER + code:59"
    assert interpretar_resultado("ESCAPE\n") is None
    assert interpretar_resultado("") is None
    assert interpretar_resultado("SUPER") is None


def test_tecla_textual():
    assert combinacao_de_tecla_textual("ctrl+shift+q").canonica == "CTRL + SHIFT + Q"
    assert combinacao_de_tecla_textual("super+f5").canonica == "SUPER + F5"
    assert combinacao_de_tecla_textual("full_stop").canonica == "PERIOD"
    assert combinacao_de_tecla_textual("less_than_sign").canonica == "LESS"
    assert combinacao_de_tecla_textual("ç").canonica == "CCEDILLA"
    assert combinacao_de_tecla_textual("escape") is None
    assert combinacao_de_tecla_textual("ctrl") is None
    assert combinacao_de_tecla_textual("") is None


def test_fluxo_com_hyprctl_falso(tmp_path, executor, monkeypatch):
    monkeypatch.setenv("HYPRLAND_INSTANCE_SIGNATURE", "x")
    arquivo = tmp_path / "troca.txt"
    cap = CapturaHyprland(HyprlandService(executor), arquivo=arquivo)
    executor.responder(["hyprctl", "eval", gerar_lua_definicao(arquivo)], "ok")
    executor.responder(["hyprctl", "eval", gerar_lua_entrar()], "ok")
    executor.responder(["hyprctl", "eval", gerar_lua_sair()], "ok")
    assert cap.iniciar()
    arquivo.write_text("SUPER + ALT + T\n")
    assert cap.esperar(timeout=1).canonica == "SUPER + ALT + T"
    assert not arquivo.exists()
    assert executor.chamadas[-1] == ("hyprctl", "eval", gerar_lua_sair())
    # 2ª vez não redefine
    n = executor.chamadas.count(("hyprctl", "eval", gerar_lua_definicao(arquivo)))
    assert cap.iniciar() and executor.chamadas.count(("hyprctl", "eval", gerar_lua_definicao(arquivo))) == n


def test_timeout_reseta(tmp_path, executor, monkeypatch):
    monkeypatch.setenv("HYPRLAND_INSTANCE_SIGNATURE", "x")
    arquivo = tmp_path / "troca.txt"
    cap = CapturaHyprland(HyprlandService(executor), arquivo=arquivo)
    for lua in (gerar_lua_definicao(arquivo), gerar_lua_entrar(), gerar_lua_sair()):
        executor.responder(["hyprctl", "eval", lua], "ok")
    assert cap.iniciar()
    assert cap.esperar(timeout=0.2) is None
    assert executor.chamadas[-1] == ("hyprctl", "eval", gerar_lua_sair())


def test_sem_hyprland_nao_tenta(tmp_path, executor, monkeypatch):
    monkeypatch.delenv("HYPRLAND_INSTANCE_SIGNATURE", raising=False)
    cap = CapturaHyprland(HyprlandService(executor), arquivo=tmp_path / "t")
    assert not cap.iniciar() and executor.chamadas == []
