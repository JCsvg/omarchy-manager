import json

from omarchy_manager.services import caminhos
from omarchy_manager.services.omarchy import OmarchyService
from omarchy_manager.services.previa_ao_vivo import PreviaAoVivo, ctrl_pressionado


def _previa(tmp_path, executor, monkeypatch):
    monkeypatch.setattr(caminhos, "PROIBIDOS", (tmp_path / "proibido",))
    estado = tmp_path / "estado"
    (estado / "theme" / "backgrounds").mkdir(parents=True)
    (estado / "theme.name").write_text("signature\n")
    fundo = estado / "theme" / "backgrounds" / "deer.png"
    fundo.write_bytes(b"x")
    (estado / "background").symlink_to(fundo)
    monkeypatch.setattr(caminhos, "OMARCHY_STATE_CURRENT", estado)
    for slug in ("tokyo-night", "gruvbox", "signature"):
        executor.responder(["omarchy", "theme", "set", slug], "")
    executor.responder(["omarchy", "theme", "bg", "set", str(fundo)], "")
    return PreviaAoVivo(OmarchyService(executor), tmp_path / "st" / "previa-original.json"), fundo


def test_grava_original_antes_de_aplicar_e_restaura(tmp_path, executor, monkeypatch):
    p, fundo = _previa(tmp_path, executor, monkeypatch)
    assert not p.ativa and not p.pendente()
    ok, msg = p.iniciar("tokyo-night")
    assert ok and msg == "" and p.ativa and p.aplicado == "tokyo-night"
    assert json.loads(p.arquivo.read_text()) == {"tema": "signature", "fundo": str(fundo)}
    p.iniciar("gruvbox")
    p.iniciar("gruvbox")  # repetido não chama de novo
    assert json.loads(p.arquivo.read_text())["tema"] == "signature"  # original não é sobrescrito
    assert [c[3] for c in executor.chamadas if c[:3] == ("omarchy", "theme", "set")] == ["tokyo-night", "gruvbox"]
    assert p.restaurar() is True
    assert executor.chamadas[-2:] == [("omarchy", "theme", "set", "signature"), ("omarchy", "theme", "bg", "set", str(fundo))]
    assert not p.ativa and not p.arquivo.exists()
    assert p.restaurar() is False  # idempotente


def test_previa_do_proprio_tema_atual_nao_chama_nada(tmp_path, executor, monkeypatch):
    p, _ = _previa(tmp_path, executor, monkeypatch)
    p.iniciar("signature")
    assert not any(c[:3] == ("omarchy", "theme", "set") for c in executor.chamadas)
    p.restaurar()
    assert not any(c[:3] == ("omarchy", "theme", "set") for c in executor.chamadas)


def test_recuperacao_apos_crash(tmp_path, executor, monkeypatch):
    p, fundo = _previa(tmp_path, executor, monkeypatch)
    p.iniciar("tokyo-night")
    # processo morreu: nova instância só tem o arquivo
    novo = PreviaAoVivo(OmarchyService(executor), p.arquivo)
    assert novo.pendente()
    assert novo.restaurar()
    assert ("omarchy", "theme", "set", "signature") in executor.chamadas
    assert not novo.pendente()


def test_manter_esquece_sem_restaurar(tmp_path, executor, monkeypatch):
    p, _ = _previa(tmp_path, executor, monkeypatch)
    p.iniciar("tokyo-night")
    p.manter()
    assert not p.ativa and not p.arquivo.exists()
    assert ("omarchy", "theme", "set", "signature") not in executor.chamadas


def test_falha_ao_restaurar_mantem_o_arquivo(tmp_path, executor, monkeypatch):
    p, _ = _previa(tmp_path, executor, monkeypatch)
    p.iniciar("tokyo-night")
    executor.responder(["omarchy", "theme", "set", "signature"], "", codigo=1, stderr="boom")
    assert p.restaurar() is False
    assert p.arquivo.exists()


def test_falha_ao_aplicar(tmp_path, executor, monkeypatch):
    p, _ = _previa(tmp_path, executor, monkeypatch)
    executor.responder(["omarchy", "theme", "set", "tokyo-night"], "", codigo=1, stderr="nope")
    ok, msg = p.iniciar("tokyo-night")
    assert not ok and "nope" in msg and p.aplicado == "signature"


def test_ctrl_sem_hyprland(monkeypatch, executor):
    from omarchy_manager.services.hyprland import HyprlandService

    monkeypatch.delenv("HYPRLAND_INSTANCE_SIGNATURE", raising=False)
    assert ctrl_pressionado(HyprlandService(executor)) is None
    monkeypatch.setenv("HYPRLAND_INSTANCE_SIGNATURE", "x")
    assert ctrl_pressionado(HyprlandService(executor)) is None  # eval falso responde 127


def test_ctrl_le_o_arquivo(monkeypatch, tmp_path):
    from omarchy_manager.services.executor import Resultado

    monkeypatch.setenv("HYPRLAND_INSTANCE_SIGNATURE", "x")
    arq = tmp_path / "ctrl.txt"

    class Falso:
        def eval_lua(self, lua, timeout=3):
            assert "Control_L" in lua and str(arq) in lua
            arq.write_text("1")
            return Resultado(("hyprctl",), 0, "ok", "")

    assert ctrl_pressionado(Falso(), arq) is True
    arq.write_text("0")
    Falso.eval_lua = lambda self, lua, timeout=3: Resultado(("hyprctl",), 0, "ok", "")
    assert ctrl_pressionado(Falso(), arq) is False
