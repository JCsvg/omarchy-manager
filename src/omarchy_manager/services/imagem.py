"""Gera a imagem do fundo no formato que o terminal entende.

Decodificar um papel de parede grande custa mais de 1 s, então cada arquivo
é reduzido uma vez para um JPEG intermediário em ~/.cache/omarchy-manager/
(chave: caminho, data e tamanho). Sixel, PNG e blocos saem desse
intermediário em décimos de segundo. Tudo aqui roda fora da thread da UI.
"""

from __future__ import annotations

import base64
import hashlib
import os
import re
import shutil
from pathlib import Path

from omarchy_manager.services.executor import ComandoAusente, executar_binario

LADO_INTERMEDIARIO = "1600x1000>"
_RE_RASTER = re.compile(rb'"\d+;\d+;(\d+);(\d+)')


def pasta_cache() -> Path:
    base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "omarchy-manager" / "miniaturas"


def _magick() -> str | None:
    return shutil.which("magick") or shutil.which("convert")


def intermediario(imagem: Path, pasta: Path | None = None) -> Path | None:
    """JPEG reduzido da imagem, criado na primeira vez e reaproveitado depois."""
    magick = _magick()
    if magick is None:
        return None
    try:
        st = imagem.stat()
    except OSError:
        return None
    chave = hashlib.sha1(f"{imagem.resolve()}|{st.st_mtime_ns}|{st.st_size}".encode()).hexdigest()
    pasta = pasta or pasta_cache()
    destino = pasta / f"{chave}.jpg"
    if destino.is_file() and destino.stat().st_size > 0:
        return destino
    pasta.mkdir(parents=True, exist_ok=True)
    tmp = pasta / f".{chave}.{os.getpid()}.jpg"
    try:
        codigo, _ = executar_binario([magick, f"{imagem}[0]", "-resize", LADO_INTERMEDIARIO, "-quality", "90", str(tmp)], timeout=40)
    except ComandoAusente:
        return None
    if codigo != 0 or not tmp.is_file():
        tmp.unlink(missing_ok=True)
        return None
    os.replace(tmp, destino)
    return destino


def sixel(origem: Path, largura_px: int, altura_px: int) -> tuple[str, int, int] | None:
    """(sequência Sixel, largura, altura em pixels), cabendo na caixa e mantendo a proporção."""
    magick = _magick()
    altura_px -= altura_px % 6  # o Sixel avança de 6 em 6 linhas; não pode passar da caixa
    if magick is None or largura_px < 8 or altura_px < 6:
        return None
    try:
        codigo, saida = executar_binario([magick, f"{origem}[0]", "-resize", f"{largura_px}x{altura_px}", "sixel:-"], timeout=30)
    except ComandoAusente:
        return None
    if codigo != 0 or not saida.startswith(b"\x1bP"):
        return None
    m = _RE_RASTER.search(saida[:200])
    larg, alt = (int(m.group(1)), int(m.group(2))) if m else (largura_px, altura_px)
    return saida.decode("ascii", "replace"), larg, alt


def kitty(origem: Path, largura_px: int, altura_px: int, id_imagem: int) -> tuple[str, int, int] | None:
    """Sequência do protocolo kitty (PNG em base64, em pedaços) que desenha na posição do cursor."""
    magick = _magick()
    if magick is None or largura_px < 8 or altura_px < 8:
        return None
    try:
        codigo, png = executar_binario([magick, f"{origem}[0]", "-resize", f"{largura_px}x{altura_px}", "png:-"], timeout=30)
    except ComandoAusente:
        return None
    if codigo != 0 or not png.startswith(b"\x89PNG"):
        return None
    larg, alt = int.from_bytes(png[16:20], "big"), int.from_bytes(png[20:24], "big")
    b64 = base64.standard_b64encode(png).decode("ascii")
    pedacos = [b64[i : i + 4096] for i in range(0, len(b64), 4096)]
    partes = []
    for i, pedaco in enumerate(pedacos):
        mais = 1 if i < len(pedacos) - 1 else 0
        cabecalho = f"a=T,f=100,i={id_imagem},q=2,C=1,z=-1,m={mais}" if i == 0 else f"m={mais}"
        partes.append(f"\x1b_G{cabecalho};{pedaco}\x1b\\")
    return "".join(partes), larg, alt


def kitty_apagar(id_imagem: int) -> str:
    return f"\x1b_Ga=d,d=I,i={id_imagem},q=2\x1b\\"


def blocos_chafa(origem: Path, colunas: int, linhas: int) -> str | None:
    """Texto ANSI do chafa com símbolos de bloco, meio bloco e quadrante (mais denso que só ▀)."""
    chafa = shutil.which("chafa")
    if chafa is None:
        return None
    try:
        codigo, saida = executar_binario(
            [chafa, "-f", "symbols", "--symbols", "block+half+quad+space", "--colors", "full", "--animate", "off",
             "--polite", "on", "--probe", "off", "--size", f"{colunas}x{linhas}", str(origem)], timeout=20)
    except ComandoAusente:
        return None
    texto = saida.decode("utf-8", "replace").strip("\n")
    return texto if codigo == 0 and texto else None
