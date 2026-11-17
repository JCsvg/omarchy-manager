"""Imagens para usar como fundo da tela sem trocar de tema.

Só lista a pasta que o usuário escolheu (com subpastas) e a guarda; quem aplica é `omarchy theme bg set`. O fundo
escolhido vale até o próximo `omarchy theme set` (o Omarchy refaz o fundo do
tema), como já acontece com o `omarchy theme bg next`.
"""

from __future__ import annotations

import os
from pathlib import Path

from omarchy_manager.services import caminhos

EXTENSOES = {".png", ".jpg", ".jpeg", ".webp"}
LIMITE = 600
PROFUNDIDADE = 3


def arquivo_pasta() -> Path:
    return caminhos.CONFIG_DIR / "fundo-pasta.txt"


def pasta_escolhida() -> Path | None:
    """A pasta que o usuário escolheu da última vez, se ainda existir."""
    try:
        linha = arquivo_pasta().read_text(encoding="utf-8").strip()
    except OSError:
        return None
    pasta = Path(linha).expanduser() if linha else None
    return pasta if pasta is not None and pasta.is_dir() else None


def definir_pasta(pasta: Path) -> None:
    arq = arquivo_pasta()
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_text(f"{Path(pasta).expanduser().resolve()}\n", encoding="utf-8")


def eh_imagem(caminho: Path) -> bool:
    return caminho.suffix.lower() in EXTENSOES and caminho.is_file()


def listar(pasta: Path | None, limite: int = LIMITE) -> list[Path]:
    """Imagens da pasta e das subpastas, até PROFUNDIDADE níveis, em ordem de nome."""
    if pasta is None or not Path(pasta).is_dir():
        return []
    raiz = Path(pasta).resolve()
    achadas: list[Path] = []
    for atual, subs, arquivos in os.walk(raiz):
        if len(Path(atual).parts) - len(raiz.parts) >= PROFUNDIDADE:
            subs[:] = []
        subs[:] = sorted(d for d in subs if not d.startswith("."))
        for nome in sorted(arquivos):
            caminho = Path(atual) / nome
            if eh_imagem(caminho):
                achadas.append(caminho)
                if len(achadas) >= limite:
                    return achadas
    return achadas
