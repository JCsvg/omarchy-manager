"""Prévia ao vivo de tema: aplica de verdade por um tempo e garante a volta.

O tema e o fundo originais são gravados em
`~/.local/state/omarchy-manager/previa-original.json` ANTES do primeiro
`omarchy theme set`. A restauração acontece ao desligar a prévia, ao trocar de
aba, ao sair, em SIGTERM/SIGHUP, em `atexit` e, se o processo morrer sem
chance de reagir, na próxima abertura do programa (o arquivo ainda existe).
"""

from __future__ import annotations

import atexit
import json
import os
import signal
import tempfile
import threading
from pathlib import Path

from omarchy_manager.services import caminhos
from omarchy_manager.services.log import logger
from omarchy_manager.services.omarchy import OmarchyService


def arquivo_estado_padrao() -> Path:
    return caminhos.STATE_DIR / "previa-original.json"


class PreviaAoVivo:
    def __init__(self, omarchy: OmarchyService, arquivo_estado: Path | None = None) -> None:
        self.omarchy = omarchy
        self._arquivo = arquivo_estado
        self._trava = threading.RLock()
        self._original: dict | None = None
        self.aplicado: str | None = None

    @property
    def arquivo(self) -> Path:
        return self._arquivo or arquivo_estado_padrao()

    @property
    def ativa(self) -> bool:
        return self._original is not None

    @property
    def tema_original(self) -> str:
        return (self._original or {}).get("tema", "")

    def pendente(self) -> bool:
        """Há estado gravado por uma sessão que não restaurou (crash, kill -9)."""
        return self._original is None and self.arquivo.is_file()

    def _gravar(self, dados: dict) -> None:
        destino = caminhos.garantir_gravavel(self.arquivo)
        destino.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=destino.parent, prefix=".previa-", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(dados, fh)
        os.replace(tmp, destino)

    def _ler(self) -> dict | None:
        try:
            dados = json.loads(self.arquivo.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return dados if isinstance(dados, dict) else None

    def iniciar(self, slug: str) -> tuple[bool, str]:
        """Aplica `slug` como prévia. Devolve (ok, mensagem)."""
        with self._trava:
            if self._original is None:
                fundo = self.omarchy.theme_bg_current_path()
                original = {"tema": self.omarchy.theme_current_slug(), "fundo": str(fundo) if fundo else ""}
                if not original["tema"]:
                    return False, "Não foi possível descobrir o tema atual; a prévia ao vivo não foi iniciada."
                self._gravar(original)  # antes de qualquer mudança
                self._original = original
                self.aplicado = original["tema"]
            if slug == self.aplicado:
                return True, ""
            r = self.omarchy.theme_set(slug)
            if not r.ok:
                return False, f"Falha na prévia de {slug}: {r.erro_legivel}"
            self.aplicado = slug
            logger.info("prévia ao vivo: %s (original %s)", slug, self._original["tema"])
            return True, ""

    def restaurar(self) -> bool:
        """Volta ao tema e ao fundo originais. Idempotente. True se restaurou algo."""
        with self._trava:
            original = self._original or self._ler()
            if original is None:
                return False
            tema, fundo = str(original.get("tema", "")), str(original.get("fundo", ""))
            ok = True
            if tema and tema != self.aplicado:
                ok = self.omarchy.theme_set(tema).ok
            if ok and fundo and Path(fundo).is_file():
                self.omarchy.theme_bg_set(Path(fundo))
            if ok:
                self.arquivo.unlink(missing_ok=True)
                self._original = None
                self.aplicado = None
                logger.info("prévia ao vivo: restaurado %s", tema)
            else:
                logger.error("prévia ao vivo: falha ao restaurar %s; estado mantido em %s", tema, self.arquivo)
            return ok

    def manter(self) -> None:
        """O usuário aplicou de vez: esquece o original sem restaurar."""
        with self._trava:
            self.arquivo.unlink(missing_ok=True)
            self._original = None
            self.aplicado = None

    def instalar_rede_de_seguranca(self) -> None:
        atexit.register(self.restaurar)

        def ao_sinal(numero, _quadro):
            try:
                self.restaurar()
            finally:
                signal.signal(numero, signal.SIG_DFL)
                os.kill(os.getpid(), numero)

        for sinal in (signal.SIGTERM, signal.SIGHUP):
            try:
                signal.signal(sinal, ao_sinal)
            except (ValueError, OSError):
                pass


def ctrl_pressionado(hyprland, arquivo: Path | None = None) -> bool | None:
    """Pergunta ao Hyprland se algum Ctrl físico está pressionado.

    O terminal não avisa quando uma tecla é solta (o Textual 8 não pede os
    eventos de soltura do protocolo kitty), então a única fonte é o compositor.
    Devolve None quando não dá para saber (sem Hyprland, erro no eval).
    """
    if not os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        return None
    base = Path(os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir())
    alvo = arquivo or base / "omarchy-manager-ctrl.txt"
    caminho = str(alvo).replace("\\", "\\\\").replace('"', '\\"')
    lua = (
        f'local f = io.open("{caminho}", "w") if f then '
        'local a, x = pcall(hl.is_key_down, "Control_L") local b, y = pcall(hl.is_key_down, "Control_R") '
        'f:write(((a and x) or (b and y)) and "1" or "0") f:close() end'
    )
    try:
        r = hyprland.eval_lua(lua, timeout=3)
    except Exception:
        return None
    if not r.ok or r.stdout.strip().startswith("error"):
        return None
    try:
        return alvo.read_text(encoding="utf-8").strip() == "1"
    except OSError:
        return None
