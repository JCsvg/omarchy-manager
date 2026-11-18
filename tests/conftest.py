from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES


class ExecutorFalso:
    """Substitui `executar`: devolve respostas pré-gravadas e registra chamadas."""

    def __init__(self) -> None:
        from omarchy_manager.services.executor import Resultado

        self._Resultado = Resultado
        self.respostas: dict[tuple[str, ...], tuple[int, str, str]] = {}
        self.chamadas: list[tuple[str, ...]] = []

    def responder(self, comando: list[str], stdout: str = "", codigo: int = 0, stderr: str = "") -> None:
        self.respostas[tuple(comando)] = (codigo, stdout, stderr)

    def __call__(self, args, **kwargs):
        chave = tuple(args)
        assert not isinstance(args, str), "comando passado como string"
        assert "shell" not in kwargs
        self.chamadas.append(chave)
        codigo, out, err = self.respostas.get(chave, (127, "", f"sem resposta falsa para {chave}"))
        return self._Resultado(chave, codigo, out, err)


@pytest.fixture
def executor() -> ExecutorFalso:
    return ExecutorFalso()


@pytest.fixture(autouse=True)
def _ambiente_isolado(tmp_path_factory, monkeypatch):
    """Nenhum teste lê ou grava o ~/.config, os .desktop, o wrapper ou o navegador padrão reais."""
    from omarchy_manager.services import caminhos

    raiz = tmp_path_factory.mktemp("isolado")
    for var, sub in (("OMARCHY_MANAGER_CHROME_DIR", "chrome"), ("OMARCHY_MANAGER_APPS_DIR", "apps"),
                     ("OMARCHY_MANAGER_BIN_DIR", "bin"), ("OMARCHY_MANAGER_PERFIS", "perfis.conf")):
        monkeypatch.setenv(var, str(raiz / sub))
    monkeypatch.setenv("OMARCHY_MANAGER_NAVEGADOR_PADRAO", "firefox.desktop")
    monkeypatch.setattr(caminhos, "CONFIG_TOML", raiz / "config.toml")
    monkeypatch.setattr(caminhos, "BACKUPS_DIR", raiz / "backups")


@pytest.fixture(autouse=True)
def _sem_abertura(tmp_path_factory, monkeypatch):
    """Testes antigos não dependem da abertura: runtime dir de teste com o marcador já gravado."""
    pasta = tmp_path_factory.mktemp("runtime")
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(pasta))
    (pasta / "omarchy-manager").mkdir()
    (pasta / "omarchy-manager" / "abertura-mostrada").write_text("1\n")
