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
