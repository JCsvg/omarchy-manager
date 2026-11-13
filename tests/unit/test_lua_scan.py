from pathlib import Path

from omarchy_manager.models import Atalho
from omarchy_manager.services import caminhos
from omarchy_manager.services.lua_scan import classificar_origem, enriquecer, interpretar

SAIDA = "\n".join(
    [
        "BIND\t64\tW\tClose window\tlua\thl.dsp.window.close()\t/usr/share/omarchy/default/hypr/bindings/tiling.lua",
        "BIND\t68\tV\tClipboard\texec\tomarchy-shell shell toggle omarchy.clipboard\t/usr/share/omarchy/default/hypr/bindings/utilities.lua",
        "BIND\t65\tcode:59\tDiminuir transparência da janela\texec\t/home/jc/.local/bin/op less\t/home/jc/.config/hypr/bindings.lua",
        "BIND\t64\tP\tPomodoro\texec\tomarchy-shell shell toggle mlhunter.pomodoro\t/home/jc/.config/omarchy/plugins/mlhunter.pomodoro/hypr.lua",
        "BIND\t64\tG\tGerenciador\texec\tomarchy-manager\t/home/jc/.config/hypr/omarchy-manager-bindings.lua",
        "UNBIND\t65\tCOMMA\t/home/jc/.config/hypr/bindings.lua",
        "lixo sem tab",
    ]
)


def test_interpretar():
    binds, unbinds = interpretar(SAIDA)
    assert len(binds) == 5 and len(unbinds) == 1
    assert binds[1].comando == "omarchy-shell shell toggle omarchy.clipboard"
    assert unbinds[0].key == "COMMA" and unbinds[0].modmask == 65


def test_classificar_origem(monkeypatch, tmp_path):
    home = tmp_path / "home"
    (home / ".config" / "hypr").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(caminhos, "HYPR_MANAGER_BINDINGS", home / ".config" / "hypr" / "omarchy-manager-bindings.lua")
    plugins = {"mlhunter.pomodoro": home / ".config" / "omarchy" / "plugins" / "mlhunter.pomodoro"}
    assert classificar_origem("/usr/share/omarchy/default/hypr/bindings/tiling.lua") == ("omarchy", "")
    assert classificar_origem(str(home / ".config/hypr/bindings.lua")) == ("usuario", "")
    assert classificar_origem(str(home / ".config/hypr/omarchy-manager-bindings.lua")) == ("gerenciador", "")
    assert classificar_origem(str(plugins["mlhunter.pomodoro"] / "hypr.lua"), plugins) == ("plugin", "mlhunter.pomodoro")
    assert classificar_origem("") == ("desconhecida", "")
    assert classificar_origem("/opt/x.lua") == ("desconhecida", "")


def test_enriquecer_casa_por_descricao_e_tecla(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: Path("/home/jc")))
    monkeypatch.setattr(caminhos, "HYPR_MANAGER_BINDINGS", Path("/home/jc/.config/hypr/omarchy-manager-bindings.lua"))
    binds, _ = interpretar(SAIDA)
    atalhos = [
        Atalho(64, "W", description="Close window", dispatcher="__lua", arg="77"),
        Atalho(65, "", keycode=59, description="Diminuir transparência da janela", dispatcher="__lua", arg="1"),
        Atalho(64, "G", description="Gerenciador", dispatcher="__lua", arg="2"),
        Atalho(64, "P", description="Pomodoro", dispatcher="__lua", arg="3"),
        Atalho(0, "XF86AudioMute", description="Mute", dispatcher="__lua", arg="4"),
    ]
    plugins = {"mlhunter.pomodoro": Path("/home/jc/.config/omarchy/plugins/mlhunter.pomodoro")}
    saida = enriquecer(atalhos, binds, plugins)
    assert saida[0].origem == "omarchy" and saida[0].comando == "hl.dsp.window.close()"
    assert saida[1].origem == "usuario" and saida[1].key == "code:59" and saida[1].dispatcher == "exec"
    assert saida[1].combinacao == "SUPER + SHIFT + code:59"
    assert saida[2].origem == "gerenciador"
    assert saida[3].origem == "plugin" and saida[3].plugin_id == "mlhunter.pomodoro"
    assert saida[4].origem == "desconhecida" and saida[4].comando == ""
