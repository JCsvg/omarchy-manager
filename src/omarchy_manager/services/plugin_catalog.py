"""PluginCatalog: junta `omarchy plugin list --json`, manifest.json e git remote.

Sem rede. Tudo vem do disco e de comandos locais.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from urllib.parse import urlparse

from omarchy_manager.models import Atalho, Plugin
from omarchy_manager.services import caminhos, traducoes
from omarchy_manager.services.executor import ComandoAusente, executar
from omarchy_manager.services.log import logger

HOSTS_GIT = ("github.com", "gitlab.com", "codeberg.org", "sr.ht", "bitbucket.org")


def normalizar_url_repositorio(bruta: str) -> str:
    """Devolve uma URL https limpa ou "" se não for reconhecida.

    Aceita `https://host/a/b(.git)`, `git@host:a/b(.git)`, `git://host/a/b`,
    `ssh://git@host/a/b`. Nunca devolve algo executável.
    """
    texto = bruta.strip()
    if not texto:
        return ""
    m = re.match(r"^(?:git@|ssh://git@)([^:/]+)[:/](.+)$", texto)
    if m:
        texto = f"https://{m.group(1)}/{m.group(2)}"
    elif texto.startswith("git://"):
        texto = "https://" + texto[len("git://") :]
    try:
        partes = urlparse(texto)
    except ValueError:
        return ""
    if partes.scheme != "https" or not partes.netloc:
        return ""
    host = partes.hostname or ""
    if not any(host == h or host.endswith("." + h) for h in HOSTS_GIT):
        return ""
    caminho = partes.path.rstrip("/")
    if caminho.endswith(".git"):
        caminho = caminho[:-4]
    if caminho.count("/") < 2:
        return ""
    return f"https://{host}{caminho}"


def _campo_url(valor) -> str:
    if isinstance(valor, str):
        return valor
    if isinstance(valor, dict):
        return str(valor.get("url", ""))
    return ""


def ler_manifesto(pasta: Path) -> tuple[dict, list[str]]:
    """Manifesto como dict e lista de campos que faltam ou estão quebrados."""
    arquivo = pasta / "manifest.json"
    faltas: list[str] = []
    try:
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}, ["manifest.json"]
    if not isinstance(dados, dict):
        return {}, ["manifest.json"]
    for campo in ("name", "description", "author", "version"):
        if not isinstance(dados.get(campo), str) or not dados[campo].strip():
            faltas.append(campo)
    return dados, faltas


class PluginCatalog:
    def __init__(self, executar_fn=executar, raiz_usuario: Path | None = None, raiz_sistema: Path | None = None,
                 traducoes: dict[str, dict[str, str]] | None = None) -> None:
        self._executar = executar_fn
        self._traducoes_fixas = traducoes
        self._traducoes: dict[str, dict[str, str]] = traducoes or {}
        self._raiz_usuario = raiz_usuario or caminhos.OMARCHY_USER_PLUGINS
        self._raiz_sistema = raiz_sistema or (caminhos.omarchy_path() / "shell" / "plugins")
        self._indice: dict[str, Path] | None = None

    def _indexar(self) -> dict[str, Path]:
        if self._indice is not None:
            return self._indice
        indice: dict[str, Path] = {}
        for raiz in (self._raiz_sistema, self._raiz_usuario):
            if not raiz.is_dir():
                continue
            for pasta in sorted(raiz.iterdir()):
                manifesto = pasta / "manifest.json"
                if not manifesto.is_file():
                    continue
                try:
                    pid = json.loads(manifesto.read_text(encoding="utf-8")).get("id")
                except (OSError, json.JSONDecodeError, AttributeError):
                    pid = None
                if isinstance(pid, str):
                    indice[pid] = pasta
                indice.setdefault(pasta.name, pasta)
        self._indice = indice
        return indice

    def invalidar(self) -> None:
        self._indice = None

    def pasta_de(self, plugin_id: str) -> Path | None:
        return self._indexar().get(plugin_id)

    def url_repositorio(self, pasta: Path | None, manifesto: dict) -> str:
        for campo in ("repository", "homepage"):
            url = normalizar_url_repositorio(_campo_url(manifesto.get(campo)))
            if url:
                return url
        if pasta is not None and (pasta / ".git").exists():
            try:
                r = self._executar(["git", "-C", str(pasta), "remote", "get-url", "origin"], timeout=5)
            except ComandoAusente:
                return ""
            if r.ok:
                return normalizar_url_repositorio(r.stdout)
        return ""

    def montar(self, bruto: dict) -> Plugin:
        pid = str(bruto.get("id", ""))
        pasta = self.pasta_de(pid)
        manifesto, faltas = ler_manifesto(pasta) if pasta else ({}, ["pasta do plugin"])
        first_party = bool(bruto.get("firstParty", False))
        # Só conta como "instalado pelo usuário" o que está na raiz do usuário.
        pasta_usuario = pasta if pasta is not None and self._raiz_usuario in pasta.parents else None
        nome_original = str(bruto.get("name") or manifesto.get("name") or pid)
        descricao_original = str(manifesto.get("description", "") or "")
        nome, descricao = traducoes.traduzir(self._traducoes, pid, nome_original, descricao_original)
        return Plugin(
            id=pid,
            name=nome,
            nome_original=nome_original,
            descricao_original=descricao_original,
            kinds=tuple(str(k) for k in bruto.get("kinds", []) or manifesto.get("kinds", [])),
            enabled=bool(bruto.get("enabled", False)),
            active=bool(bruto.get("active", False)),
            can_disable=bool(bruto.get("canDisable", True)),
            first_party=first_party,
            cloned_from=str(bruto.get("clonedFrom", "") or ""),
            path=pasta_usuario if not first_party else pasta,
            description=descricao,
            author=str(manifesto.get("author", "") or ""),
            version=str(manifesto.get("version", "") or ""),
            repository_url=self.url_repositorio(pasta, manifesto),
            metadados_incompletos=tuple(faltas),
        )

    def listar(self, brutos: list[dict]) -> list[Plugin]:
        self.invalidar()
        self._traducoes = self._traducoes_fixas if self._traducoes_fixas is not None else traducoes.carregar()
        plugins = [self.montar(b) for b in brutos if isinstance(b, dict) and b.get("id")]
        logger.debug("catálogo: %d plugins", len(plugins))
        return sorted(plugins, key=lambda p: (p.first_party, p.name.lower()))


# Relação plugin <-> atalhos (plano 7.3)


def ler_aliases(arquivo: Path | None = None) -> dict[str, list[str]]:
    """`plugin-shortcuts.toml`: [aliases] "<plugin-id>" = ["trecho", ...]."""
    caminho = arquivo or caminhos.PLUGIN_SHORTCUTS_TOML
    try:
        with open(caminho, "rb") as fh:
            dados = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    aliases = dados.get("aliases", {})
    if not isinstance(aliases, dict):
        return {}
    saida: dict[str, list[str]] = {}
    for pid, valores in aliases.items():
        if isinstance(valores, str):
            saida[str(pid)] = [valores]
        elif isinstance(valores, list):
            saida[str(pid)] = [str(v) for v in valores if isinstance(v, str)]
    return saida


_PADRAO_SHELL = re.compile(r"omarchy-shell\s+(?:-q\s+)?(?:shell\s+)?(?:toggle|open|show|panel|overlay|menu)\w*\s+'?\"?([A-Za-z0-9_.\-]+)")


def atalhos_do_plugin(plugin_id: str, atalhos: list[Atalho], aliases: dict[str, list[str]] | None = None) -> list[Atalho]:
    """Atalhos cuja relação com o plugin pode ser provada (ordem do plano 7.3)."""
    trechos = [plugin_id] + list((aliases or {}).get(plugin_id, []))
    encontrados: list[Atalho] = []
    for a in atalhos:
        if a.plugin_id == plugin_id:
            encontrados.append(a)
            continue
        texto = " ".join(x for x in (a.comando, a.arg) if x and x != "__lua")
        if not texto:
            continue
        m = _PADRAO_SHELL.search(texto)
        if m and m.group(1) == plugin_id:
            encontrados.append(a)
            continue
        if any(t and t in texto for t in trechos):
            encontrados.append(a)
    return encontrados
