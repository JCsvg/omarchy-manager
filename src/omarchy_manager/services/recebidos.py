"""Onde cai o que chega pela aba Compartilhar: pasta de downloads do app.

Nada é executado e nada é sobrescrito sem pergunta: se o destino existe, levanta
`JaExiste` e quem chama decide; com `sobrescrever=True`, o antigo vai para o backup.
"""

from __future__ import annotations

import os
import shutil
from datetime import datetime
from pathlib import Path

from omarchy_manager.services import caminhos
from omarchy_manager.services.bundle import ErroBundle, extrair_para_temporario


def pasta_downloads() -> Path:
    return Path.home() / "Downloads" / "omarchy-manager"


class JaExiste(FileExistsError):
    def __init__(self, destino: Path) -> None:
        super().__init__(str(destino))
        self.destino = destino


def nome_seguro(nome: str) -> str:
    n = os.path.basename(nome.replace("\\", "/")).strip().replace("\x00", "")
    if n in ("", ".", ".."):
        raise ErroBundle(f"nome de arquivo inválido: {nome!r}")
    return n[:200]


def _preparar_destino(base: Path, nome: str, sobrescrever: bool) -> Path:
    base.mkdir(parents=True, exist_ok=True)
    destino = caminhos.garantir_gravavel(base / nome_seguro(nome))
    try:
        destino.relative_to(base.resolve())
    except ValueError as exc:
        raise ErroBundle("destino fora da pasta de downloads") from exc
    if destino.exists() or destino.is_symlink():
        if not sobrescrever:
            raise JaExiste(destino)
        caminhos.BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
        shutil.move(str(destino), str(caminhos.BACKUPS_DIR / f"{destino.name}.{datetime.now().strftime('%Y%m%d-%H%M%S')}"))
    return destino


def guardar_arquivo(origem: Path, nome: str, base: Path | None = None, *, sobrescrever: bool = False) -> Path:
    destino = _preparar_destino(base or pasta_downloads(), nome, sobrescrever)
    shutil.move(str(origem), str(destino))
    destino.chmod(0o644)  # nunca executável
    return destino


def guardar_pasta(bundle_arq: Path, sha256: str, nome: str, base: Path | None = None, *, sobrescrever: bool = False) -> Path:
    """Valida o bundle de pasta, extrai e move para <base>/<nome>."""
    destino_final = (base or pasta_downloads()) / nome_seguro(nome)
    if (destino_final.exists() or destino_final.is_symlink()) and not sobrescrever:
        raise JaExiste(destino_final)
    tmp, man = extrair_para_temporario(bundle_arq, sha256)
    if man.tipo != "pasta":
        shutil.rmtree(tmp, ignore_errors=True)
        raise ErroBundle("o pacote não é de uma pasta")
    try:
        destino = _preparar_destino(base or pasta_downloads(), nome, sobrescrever)
        shutil.move(str(tmp), str(destino))
        destino.chmod(0o755)
        for p in destino.rglob("*"):
            if p.is_file():
                p.chmod(0o644)  # nada recebido fica executável
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return destino
