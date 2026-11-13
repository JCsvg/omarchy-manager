import json

from omarchy_manager.services.hyprland import HyprlandService, atalhos_de_texto, marcar_duplicados
from omarchy_manager.services.teclas import normalizar


def test_le_binds_json(executor, fixtures):
    executor.responder(["hyprctl", "binds", "-j"], (fixtures / "binds.json").read_text())
    atalhos = HyprlandService(executor).atalhos()
    assert len(atalhos) == 6
    fechar = next(a for a in atalhos if a.description == "Close window")
    assert fechar.combinacao == "SUPER + W"
    assert fechar.dispatcher == "__lua"


def test_fallback_texto_quando_json_invalido(executor):
    executor.responder(["hyprctl", "binds", "-j"], "[{quebrado")
    executor.responder(
        ["hyprctl", "binds"],
        "bind\n\tmodmask: 64\n\tsubmap: \n\tkey: Q\n\tkeycode: 0\n\tdescription: Fechar\n\tdispatcher: __lua\n\targ: 1\n\n",
    )
    atalhos = HyprlandService(executor).atalhos()
    assert len(atalhos) == 1 and atalhos[0].key == "Q" and atalhos[0].modmask == 64


def test_parser_texto_varios():
    texto = "bind\n\tmodmask: 0\n\tkey: Print\n\tdescription: Shot\nbind\n\tmodmask: 65\n\tkey: \n\tkeycode: 59\n\tdescription: X\n"
    a = atalhos_de_texto(texto)
    assert [x.combinacao for x in a] == ["PRINT", "SUPER + SHIFT + code:59"]


def test_duplicados_marcados(fixtures):
    dados = json.loads((fixtures / "binds.json").read_text())
    from omarchy_manager.services.hyprland import atalhos_de_json

    atalhos = marcar_duplicados(atalhos_de_json(json.dumps(dados)))
    dup = [a.description for a in atalhos if a.duplicado]
    assert sorted(dup) == ["Antigo Alt+Tab", "Reveal active window"]


def test_usos_detecta_conflito(executor, fixtures):
    executor.responder(["hyprctl", "binds", "-j"], (fixtures / "binds.json").read_text())
    svc = HyprlandService(executor)
    usos = svc.usos(normalizar("super + w"))
    assert [u.description for u in usos] == ["Close window"]
    assert svc.usos(normalizar("super + ctrl + alt + shift + f24")) == []


def test_configerrors_vazio_e_com_erro(executor):
    executor.responder(["hyprctl", "configerrors"], "\n\n")
    assert HyprlandService(executor).configerrors() == []
    executor.responder(["hyprctl", "configerrors"], "config error in file x.lua: boom\n")
    assert HyprlandService(executor).configerrors() == ["config error in file x.lua: boom"]
