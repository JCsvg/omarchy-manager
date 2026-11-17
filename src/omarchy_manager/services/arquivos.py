"""Escrita segura de arquivos de configuração do usuário: backup antes, troca atômica."""

from __future__ import annotations

import os
import shutil
import tempfile
import time
from pathlib import Path

from omarchy_manager.services import caminhos


def _prefixo(destino: Path) -> str:
    return f"{destino.name}."


def fazer_backup(destino: Path) -> Path | None:
    """Copia `destino` para a pasta de backups. Devolve a cópia ou None se não havia arquivo."""
    origem = Path(destino).expanduser().resolve()
    if not origem.is_file():
        return None
    caminhos.BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    copia = caminhos.BACKUPS_DIR / f"{origem.name}.{time.strftime('%Y%m%d-%H%M%S')}"
    n = 1
    while copia.exists():  # dois backups no mesmo segundo
        n += 1
        copia = caminhos.BACKUPS_DIR / f"{origem.name}.{time.strftime('%Y%m%d-%H%M%S')}-{n}"
    shutil.copy2(origem, copia)
    return copia


def ultimo_backup(destino: Path) -> Path | None:
    nome = Path(destino).name
    if not caminhos.BACKUPS_DIR.is_dir():
        return None
    achados = sorted(p for p in caminhos.BACKUPS_DIR.iterdir() if p.name.startswith(f"{nome}.") and p.is_file())
    return achados[-1] if achados else None


def gravar(destino: Path, texto: str) -> Path | None:
    """Grava `texto` em `destino` (seguindo link simbólico) depois de fazer backup."""
    alvo = caminhos.garantir_gravavel(destino)
    backup = fazer_backup(alvo)
    alvo.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=alvo.parent, prefix=f".{alvo.name}.", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(texto)
    if alvo.exists():
        shutil.copymode(alvo, tmp)
    os.replace(tmp, alvo)
    return backup


def restaurar_ultimo(destino: Path) -> Path | None:
    """Volta `destino` para o backup mais recente. O estado atual também vira backup."""
    backup = ultimo_backup(destino)
    if backup is None:
        return None
    gravar(destino, backup.read_text(encoding="utf-8"))
    return backup
