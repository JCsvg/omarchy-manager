"""Execução de subprocessos sempre com argumentos em lista.

Regra inegociável do plano (seções 2 e 12): nunca `shell=True`, nunca
comando montado por concatenação de texto, nunca URL executada como comando.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from dataclasses import dataclass

from omarchy_manager.services.log import logger

TEMPO_PADRAO = 20.0


class ComandoAusente(RuntimeError):
    """O executável não está instalado ou não está no PATH."""


@dataclass(frozen=True)
class Resultado:
    comando: tuple[str, ...]
    codigo: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.codigo == 0

    @property
    def erro_legivel(self) -> str:
        texto = self.stderr.strip() or self.stdout.strip()
        return texto or f"saiu com código {self.codigo}"


def _validar(args: Sequence[str]) -> tuple[str, ...]:
    if isinstance(args, (str, bytes)):
        raise TypeError("comando deve ser uma lista de argumentos, nunca uma string")
    lista = tuple(args)
    if not lista:
        raise ValueError("comando vazio")
    for item in lista:
        if not isinstance(item, str):
            raise TypeError(f"argumento não textual: {item!r}")
    if lista[0].startswith(("http://", "https://", "git@", "git://")):
        raise ValueError("URL nunca é executada como comando")
    return lista


def executar(
    args: Sequence[str],
    *,
    timeout: float = TEMPO_PADRAO,
    entrada: str | None = None,
    env: dict[str, str] | None = None,
    cwd: str | None = None,
) -> Resultado:
    """Roda `args` sem shell e devolve um Resultado, nunca levanta por código != 0."""
    lista = _validar(args)
    try:
        proc = subprocess.run(
            lista,
            input=entrada,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            cwd=cwd,
            check=False,
        )
    except FileNotFoundError as exc:
        logger.warning("comando ausente: %s", lista[0])
        raise ComandoAusente(f"comando não encontrado: {lista[0]}") from exc
    except subprocess.TimeoutExpired:
        logger.warning("tempo esgotado (%ss): %s", timeout, " ".join(lista))
        return Resultado(lista, 124, "", f"tempo esgotado após {timeout:g}s")
    logger.debug("exec rc=%s: %s", proc.returncode, " ".join(lista))
    return Resultado(lista, proc.returncode, proc.stdout, proc.stderr)


def executar_binario(args: Sequence[str], *, timeout: float = TEMPO_PADRAO) -> tuple[int, bytes]:
    """Como `executar`, mas devolve stdout em bytes (imagens, Sixel)."""
    lista = _validar(args)
    try:
        proc = subprocess.run(lista, capture_output=True, timeout=timeout, check=False)
    except FileNotFoundError as exc:
        raise ComandoAusente(f"comando não encontrado: {lista[0]}") from exc
    except subprocess.TimeoutExpired:
        return 124, b""
    return proc.returncode, proc.stdout


def abrir_desanexado(args: Sequence[str], *, cwd: str | None = None) -> None:
    """Abre um programa (navegador, terminal) sem esperar por ele."""
    lista = _validar(args)
    logger.info("abrir: %s", " ".join(lista))
    subprocess.Popen(
        lista,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
