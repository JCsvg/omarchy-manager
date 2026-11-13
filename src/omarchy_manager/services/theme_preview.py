"""Prévia de imagem: Sixel quando o terminal aguenta, blocos coloridos como
fallback. Sem PIL: o ImageMagick reduz a imagem e devolve um PPM P6 que é
lido aqui mesmo. `chafa` é usado se existir."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from omarchy_manager.services.executor import ComandoAusente, executar_binario


def terminal_suporta_sixel() -> bool:
    programa = os.environ.get("TERM_PROGRAM", "").lower()
    term = os.environ.get("TERM", "").lower()
    return programa == "foot" or term.startswith("foot") or term.startswith("mlterm")


def _magick() -> str | None:
    return shutil.which("magick") or shutil.which("convert")


def ler_ppm(dados: bytes) -> tuple[int, int, bytes] | None:
    """PPM P6 (cabeçalho em ASCII, pixels RGB 8 bits)."""
    partes = dados.split(maxsplit=4)
    if len(partes) < 5 or partes[0] != b"P6":
        return None
    try:
        largura, altura, maximo = int(partes[1]), int(partes[2]), int(partes[3])
    except ValueError:
        return None
    if maximo != 255 or largura <= 0 or altura <= 0:
        return None
    pixels = partes[4]
    if len(pixels) < largura * altura * 3:
        return None
    return largura, altura, pixels[: largura * altura * 3]


def blocos_de_ppm(dados: bytes) -> list[str] | None:
    """Converte um PPM em linhas de marcação Rich: 1 célula = 2 pixels na
    vertical, com `▀` colorido em frente e fundo."""
    lido = ler_ppm(dados)
    if lido is None:
        return None
    largura, altura, pix = lido

    def cor(x: int, y: int) -> str:
        i = (y * largura + x) * 3
        return f"#{pix[i]:02x}{pix[i + 1]:02x}{pix[i + 2]:02x}"

    linhas = []
    for y in range(0, altura - 1, 2):
        partes = []
        for x in range(largura):
            partes.append(f"[{cor(x, y)} on {cor(x, y + 1)}]▀[/]")
        linhas.append("".join(partes))
    return linhas


def blocos_de_imagem(imagem: Path, largura: int = 40, altura_linhas: int = 12) -> list[str] | None:
    """Prévia em blocos com `largura` colunas e `altura_linhas` linhas."""
    magick = _magick()
    if magick is None or not imagem.is_file():
        return None
    altura_px = max(2, altura_linhas * 2)
    try:
        codigo, saida = executar_binario(
            [magick, f"{imagem}[0]", "-resize", f"{largura}x{altura_px}!", "-depth", "8", "ppm:-"], timeout=20
        )
    except ComandoAusente:
        return None
    if codigo != 0:
        return None
    return blocos_de_ppm(saida)


def sixel_de_imagem(imagem: Path, largura_px: int = 400) -> bytes | None:
    """Bytes Sixel prontos para `sys.stdout.buffer`, ou None."""
    if not imagem.is_file():
        return None
    chafa = shutil.which("chafa")
    if chafa:
        try:
            codigo, saida = executar_binario([chafa, "-f", "sixel", "--probe", "off", "--size", f"{largura_px // 8}x", str(imagem)], timeout=20)
        except ComandoAusente:
            codigo, saida = 1, b""
        if codigo == 0 and saida:
            return saida
    magick = _magick()
    if magick is None:
        return None
    try:
        codigo, saida = executar_binario([magick, f"{imagem}[0]", "-resize", f"{largura_px}x", "sixel:-"], timeout=30)
    except ComandoAusente:
        return None
    return saida if codigo == 0 and saida.startswith(b"\x1bP") else None
