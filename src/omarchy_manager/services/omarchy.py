"""OmarchyService: encapsula os comandos oficiais `omarchy ...`.

Trata JSON, timeouts, código de saída e mensagens em português. Não decide
nada sobre a interface, só devolve dados ou erros legíveis.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from omarchy_manager.services import caminhos
from omarchy_manager.services.executor import ComandoAusente, Resultado, executar
from omarchy_manager.services.log import logger


class ErroOmarchy(RuntimeError):
    pass


@dataclass(frozen=True)
class Deteccao:
    omarchy: bool
    hyprland: bool
    omarchy_path: Path

    @property
    def mensagem(self) -> str:
        if self.omarchy and self.hyprland:
            return "Omarchy e Hyprland detectados"
        faltas = []
        if not self.omarchy:
            faltas.append("comando `omarchy`")
        if not self.hyprland:
            faltas.append("sessão do Hyprland")
        return "não encontrado: " + ", ".join(faltas)


def slug_de_nome(nome: str) -> str:
    """Inverso do `sed` de omarchy-theme-list: "Tokyo Night" -> "tokyo-night"."""
    return re.sub(r"\s+", "-", nome.strip()).lower()


class OmarchyService:
    def __init__(self, executar_fn=executar) -> None:
        self._executar = executar_fn

    def detectar(self) -> Deteccao:
        import os

        return Deteccao(
            omarchy=shutil.which("omarchy") is not None,
            hyprland=bool(os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")) and shutil.which("hyprctl") is not None,
            omarchy_path=caminhos.omarchy_path(),
        )

    def _rodar(self, *args: str, timeout: float = 20.0) -> Resultado:
        try:
            return self._executar(["omarchy", *args], timeout=timeout)
        except ComandoAusente as exc:
            raise ErroOmarchy("o comando `omarchy` não está instalado") from exc

    # Plugins

    def plugin_list_json(self) -> list[dict]:
        r = self._rodar("plugin", "list", "--json")
        if not r.ok:
            raise ErroOmarchy(f"`omarchy plugin list --json` falhou: {r.erro_legivel}")
        try:
            dados = json.loads(r.stdout or "[]")
        except json.JSONDecodeError as exc:
            raise ErroOmarchy("`omarchy plugin list --json` devolveu JSON inválido") from exc
        if not isinstance(dados, list):
            raise ErroOmarchy("`omarchy plugin list --json` não devolveu uma lista")
        return dados

    def plugin_enable(self, plugin_id: str) -> Resultado:
        logger.info("plugin enable %s", plugin_id)
        return self._rodar("plugin", "enable", plugin_id)

    def plugin_disable(self, plugin_id: str) -> Resultado:
        logger.info("plugin disable %s", plugin_id)
        return self._rodar("plugin", "disable", plugin_id)

    def plugin_remove(self, plugin_id: str, *, confirmado: bool) -> Resultado:
        """Remove só com `confirmado=True`, vindo de um diálogo visível."""
        if not confirmado:
            raise ErroOmarchy("remoção exige confirmação explícita")
        logger.info("plugin remove %s", plugin_id)
        # --yes só depois da nossa confirmação própria, para o comando não
        # travar esperando um terminal interativo.
        return self._rodar("plugin", "remove", plugin_id, "--yes", timeout=60)

    def plugin_validate(self, pasta: Path) -> Resultado:
        return self._rodar("plugin", "validate", str(pasta))

    # Temas

    def theme_list(self) -> list[str]:
        r = self._rodar("theme", "list")
        if not r.ok:
            raise ErroOmarchy(f"`omarchy theme list` falhou: {r.erro_legivel}")
        return [linha.strip() for linha in r.stdout.splitlines() if linha.strip()]

    def theme_dir(self, slug: str) -> Path:
        r = self._rodar("theme", "dir", slug)
        if not r.ok or not r.stdout.strip():
            raise ErroOmarchy(f"`omarchy theme dir {slug}` falhou: {r.erro_legivel}")
        return Path(r.stdout.strip())

    def theme_current_slug(self) -> str:
        """Lê o arquivo de estado que o próprio `omarchy theme current` usa."""
        arquivo = caminhos.OMARCHY_STATE_CURRENT / "theme.name"
        try:
            return arquivo.read_text(encoding="utf-8").strip()
        except OSError:
            r = self._rodar("theme", "current")
            return slug_de_nome(r.stdout) if r.ok else ""

    def theme_set(self, slug: str) -> Resultado:
        logger.info("theme set %s", slug)
        return self._rodar("theme", "set", slug, timeout=120)

    def theme_bg_set(self, imagem: Path) -> Resultado:
        logger.info("theme bg set %s", imagem)
        return self._rodar("theme", "bg", "set", str(imagem), timeout=60)

    def theme_bg_current_path(self) -> Path | None:
        link = caminhos.OMARCHY_STATE_CURRENT / "background"
        try:
            return link.resolve(strict=True)
        except OSError:
            return None
