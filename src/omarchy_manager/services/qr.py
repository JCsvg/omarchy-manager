"""QR Code em blocos Unicode de meia altura, para a TUI e para o terminal.

Usa a biblioteca `qrcode` (extra/python-qrcode) quando existe; senão o
`qrencode -t UTF8` do sistema; senão devolve None e quem chama mostra o texto.
"""

from __future__ import annotations

import shutil

from omarchy_manager.services.executor import ComandoAusente, executar


def matriz_qr(dado: str) -> list[list[bool]] | None:
    try:
        import qrcode
    except ImportError:
        return None
    qr = qrcode.QRCode(border=2, error_correction=qrcode.constants.ERROR_CORRECT_L)
    qr.add_data(dado)
    qr.make(fit=True)
    return [list(linha) for linha in qr.get_matrix()]


def linhas_de_matriz(matriz: list[list[bool]]) -> list[str]:
    """2 linhas da matriz por linha de texto: ▀ ▄ █ e espaço. Módulo escuro = bloco."""
    if len(matriz) % 2:
        matriz = matriz + [[False] * len(matriz[0])]
    simbolos = {(False, False): " ", (True, False): "▀", (False, True): "▄", (True, True): "█"}
    return ["".join(simbolos[(a, b)] for a, b in zip(matriz[i], matriz[i + 1])) for i in range(0, len(matriz), 2)]


def qr_linhas(dado: str) -> list[str] | None:
    """Linhas do QR para desenhar em preto sobre branco, ou None se não houver gerador."""
    matriz = matriz_qr(dado)
    if matriz is not None:
        return linhas_de_matriz(matriz)
    if shutil.which("qrencode"):
        try:
            r = executar(["qrencode", "-t", "UTF8", "-m", "2", "-l", "L", "--", dado], timeout=10)
        except ComandoAusente:
            return None
        if r.ok and r.stdout.strip():
            # O UTF8 do qrencode já vem invertido para fundo escuro; desinverte.
            troca = str.maketrans({"█": " ", " ": "█", "▀": "▄", "▄": "▀"})
            return [linha.translate(troca) for linha in r.stdout.splitlines() if linha]
    return None


def qr_markup(dado: str) -> str | None:
    """Markup Rich: preto sobre branco, legível em tema claro ou escuro."""
    linhas = qr_linhas(dado)
    if linhas is None:
        return None
    return "\n".join(f"[#000000 on #ffffff]{linha}[/]" for linha in linhas)


def qr_ansi(dado: str) -> str | None:
    linhas = qr_linhas(dado)
    if linhas is None:
        return None
    return "\n".join(f"\x1b[30;107m{linha}\x1b[0m" for linha in linhas)
