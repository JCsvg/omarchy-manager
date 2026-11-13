"""O que o terminal sabe desenhar: Sixel, protocolo gráfico kitty ou nada.

A resposta vem de uma consulta ao próprio terminal, feita uma vez antes de o
Textual assumir a entrada: protocolo kitty (APC de consulta), tamanho da
célula (`CSI 16 t`) e atributos primários (`CSI c`, que lista o 4 quando há
Sixel e serve de sentinela, porque todo terminal responde a ela). O nome do
terminal só entra na mensagem que explica por que a imagem ficou em blocos.
"""

from __future__ import annotations

import fcntl
import os
import re
import select
import struct
import sys
import termios
import time
import tty
from dataclasses import dataclass

CONSULTA = b"\x1b_Gi=31,s=1,v=1,a=q,t=d,f=24;AAAA\x1b\\" + b"\x1b[16t" + b"\x1b[c"
_RE_DA1 = re.compile(rb"\x1b\[\?([0-9;]*)c")
_RE_CELULA = re.compile(rb"\x1b\[6;(\d+);(\d+)t")
_RE_KITTY = re.compile(rb"\x1b_Gi=31;([^\x1b]*)\x1b\\")


@dataclass(frozen=True)
class Capacidades:
    sixel: bool = False
    kitty: bool = False
    cel_l: int = 0
    cel_a: int = 0
    consultado: bool = False
    respondeu: bool = False


_cache: Capacidades | None = None


def interpretar_resposta(dados: bytes) -> tuple[bool, bool, int, int, bool]:
    """(sixel, kitty, largura da célula, altura da célula, respondeu ao DA1)."""
    sixel = respondeu = False
    m = _RE_DA1.search(dados)
    if m:
        respondeu = True
        sixel = "4" in m.group(1).decode("ascii", "replace").split(";")
    k = _RE_KITTY.search(dados)
    kitty = bool(k and k.group(1).startswith(b"OK"))
    c = _RE_CELULA.search(dados)
    cel_a, cel_l = (int(c.group(1)), int(c.group(2))) if c else (0, 0)
    return sixel, kitty, cel_l, cel_a, respondeu


def _celula_por_ioctl() -> tuple[int, int]:
    try:
        fd = sys.__stdout__.fileno()
        linhas, colunas, larg_px, alt_px = struct.unpack("HHHH", fcntl.ioctl(fd, termios.TIOCGWINSZ, b"\0" * 8))
    except (OSError, ValueError, AttributeError):
        return 0, 0
    if not (linhas and colunas and larg_px and alt_px):
        return 0, 0
    return larg_px // colunas, alt_px // linhas


def sondar(timeout: float = 0.6) -> Capacidades:
    """Consulta o terminal. Chamar antes de `App.run()`. O resultado fica em cache."""
    global _cache
    if _cache is not None:
        return _cache
    caps = Capacidades(consultado=True)
    try:
        entrada, saida = sys.__stdin__.fileno(), sys.__stdout__.fileno()
        eh_tty = os.isatty(entrada) and os.isatty(saida)
    except (OSError, ValueError, AttributeError):
        eh_tty = False
    if eh_tty:
        antigo = termios.tcgetattr(entrada)
        buf = b""
        try:
            tty.setcbreak(entrada)
            os.write(saida, CONSULTA)
            fim = time.monotonic() + timeout
            while time.monotonic() < fim:
                pronto, _, _ = select.select([entrada], [], [], max(0.0, fim - time.monotonic()))
                if not pronto:
                    break
                buf += os.read(entrada, 4096)
                if _RE_DA1.search(buf):
                    break
        except OSError:
            pass
        finally:
            termios.tcsetattr(entrada, termios.TCSANOW, antigo)
        sixel, kitty, cel_l, cel_a, respondeu = interpretar_resposta(buf)
        if not (cel_l and cel_a):
            cel_l, cel_a = _celula_por_ioctl()
        caps = Capacidades(sixel, kitty, cel_l, cel_a, True, respondeu)
    _cache = caps
    return caps


def capacidades() -> Capacidades:
    return _cache or Capacidades()


def definir(caps: Capacidades | None) -> None:
    """Para testes e para forçar um modo."""
    global _cache
    _cache = caps


def tamanho_celula() -> tuple[int, int]:
    """Tamanho atual da célula em pixels (muda com o zoom da fonte); (0, 0) se desconhecido."""
    l, a = _celula_por_ioctl()
    if l and a:
        return l, a
    c = capacidades()
    return c.cel_l, c.cel_a


def protocolo() -> str | None:
    """"kitty", "sixel" ou None. `OMARCHY_MANAGER_IMAGEM=blocos|sixel|kitty` força."""
    forcado = os.environ.get("OMARCHY_MANAGER_IMAGEM", "").strip().lower()
    if forcado in ("blocos", "bloco", "nenhum"):
        return None
    if forcado in ("sixel", "kitty"):
        return forcado if all(tamanho_celula()) else None
    c = capacidades()
    if not all(tamanho_celula()):
        return None
    if c.kitty:
        return "kitty"
    if c.sixel:
        return "sixel"
    return None


def nome_do_terminal() -> str:
    partes = []
    for var in ("TERM_PROGRAM", "TERM"):
        valor = os.environ.get(var, "")
        if valor and valor not in partes:
            partes.append(valor)
    if os.environ.get("TMUX"):
        partes.append("dentro do tmux")
    if os.environ.get("SSH_CONNECTION"):
        partes.append("por ssh")
    return ", ".join(partes) or "desconhecido"


def motivo_blocos() -> str:
    """Frase curta que explica por que a imagem não saiu em pixels."""
    if os.environ.get("OMARCHY_MANAGER_IMAGEM", "").strip().lower() in ("blocos", "bloco", "nenhum"):
        return "Imagem em blocos: forçado por OMARCHY_MANAGER_IMAGEM."
    c = capacidades()
    if not c.consultado:
        return "Imagem em blocos: o terminal não foi consultado."
    if not c.respondeu:
        return f"Imagem em blocos: o terminal ({nome_do_terminal()}) não respondeu à consulta de gráficos."
    if not (c.sixel or c.kitty):
        return f"Imagem em blocos: o terminal ({nome_do_terminal()}) não anunciou Sixel nem o protocolo kitty."
    if not all(tamanho_celula()):
        return "Imagem em blocos: o terminal não informou o tamanho da célula em pixels."
    return ""
