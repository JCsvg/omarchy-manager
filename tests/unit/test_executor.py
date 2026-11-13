import subprocess

import pytest

from omarchy_manager.services import executor


def test_recusa_string():
    with pytest.raises(TypeError):
        executor.executar("omarchy plugin list")


def test_recusa_url_como_comando():
    with pytest.raises(ValueError):
        executor.executar(["https://github.com/x/y"])


def test_nunca_usa_shell(monkeypatch):
    capturado = {}

    def falso_run(args, **kwargs):
        capturado["args"] = args
        capturado["kwargs"] = kwargs
        return subprocess.CompletedProcess(args, 0, "ok\n", "")

    monkeypatch.setattr(executor.subprocess, "run", falso_run)
    r = executor.executar(["echo", "a b; rm -rf /"])
    assert r.ok and r.stdout == "ok\n"
    assert capturado["args"] == ("echo", "a b; rm -rf /")
    assert "shell" not in capturado["kwargs"]


def test_comando_ausente():
    with pytest.raises(executor.ComandoAusente):
        executor.executar(["comando-que-nao-existe-omgr"])


def test_timeout_vira_resultado_124():
    r = executor.executar(["sleep", "5"], timeout=0.2)
    assert r.codigo == 124
    assert "tempo esgotado" in r.stderr
