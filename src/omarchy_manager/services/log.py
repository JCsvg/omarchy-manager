"""Log de operações em ~/.local/state/omarchy-manager/manager.log.

Sem tokens, sem dados privados: só comandos, códigos de saída e caminhos.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from omarchy_manager.services import caminhos

logger = logging.getLogger("omarchy_manager")


def configurar_log(nivel: int = logging.INFO) -> None:
    if logger.handlers:
        return
    caminhos.STATE_DIR.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(caminhos.LOG_FILE, maxBytes=512_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(nivel)
