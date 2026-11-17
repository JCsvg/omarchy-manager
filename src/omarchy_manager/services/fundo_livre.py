"""Imagens para usar como fundo da tela sem trocar de tema.

Só lista e guarda pastas extras; quem aplica é `omarchy theme bg set`. O fundo
escolhido vale até o próximo `omarchy theme set` (o Omarchy refaz o fundo do
tema), como já acontece com o `omarchy theme bg next`.
"""

from __future__ import annotations

import os
from pathlib import Path

from omarchy_manager.services import caminhos

EXTENSOES = {".png", ".jpg", ".jpeg", ".webp"}
PROFUNDIDADE = 3
LIMITE = 600


def arquivo_pastas() -> Path:
    return caminhos.CONFIG_DIR / "fundos-pastas.txt"


def pastas_extras() -> list[Path]:
    try:
        linhas = arquivo_pastas().read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    return [Path(linha.strip()).expanduser() for linha in linhas if linha.strip()]


def pastas_padrao() -> list[Path]:
    casa = Path.home()
    return [
        casa / "Pictures",
        casa / "Imagens",
        casa / "Wallpapers",
        caminhos.OMARCHY_USER_BACKGROUNDS,
        *pastas_extras(),
    ]


def adicionar_pasta(pasta: Path) -> None:
    pasta = Path(pasta).expanduser().resolve()
    if pasta in [p.resolve() for p in pastas_extras()]:
        return
    arq = arquivo_pastas()
    arq.parent.mkdir(parents=True, exist_ok=True)
    with arq.open("a", encoding="utf-8") as fh:
        fh.write(f"{pasta}\n")


def eh_imagem(caminho: Path) -> bool:
    return caminho.suffix.lower() in EXTENSOES and caminho.is_file()


def listar(pastas: list[Path] | None = None, limite: int = LIMITE) -> list[Path]:
    """Imagens das pastas, sem repetir e sem passar de `PROFUNDIDADE` níveis."""
    achadas: dict[Path, None] = {}
    for pasta in pastas if pastas is not None else pastas_padrao():
        pasta = Path(pasta).expanduser()
        if not pasta.is_dir():
            continue
        base = len(pasta.resolve().parts)
        for raiz, subs, arquivos in os.walk(pasta.resolve()):
            if len(Path(raiz).parts) - base >= PROFUNDIDADE:
                subs[:] = []
            subs[:] = sorted(s for s in subs if not s.startswith("."))
            for nome in sorted(arquivos):
                caminho = Path(raiz) / nome
                if eh_imagem(caminho):
                    achadas[caminho] = None
                    if len(achadas) >= limite:
                        return list(achadas)
    return list(achadas)
