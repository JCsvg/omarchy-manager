"""Descobre comando e arquivo de origem dos binds Lua que o `hyprctl binds`
só reporta como `__lua`. Roda o `lua_scan.lua` em um `lua -E` separado; nada
é enviado ao compositor."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from omarchy_manager.models import Atalho, Origem
from omarchy_manager.services import caminhos
from omarchy_manager.services.executor import ComandoAusente, executar
from omarchy_manager.services.log import logger
from omarchy_manager.services.teclas import Combinacao

STUB = Path(__file__).with_name("lua_scan.lua")


@dataclass(frozen=True)
class BindFonte:
    modmask: int
    key: str
    description: str
    kind: str
    comando: str
    arquivo: str

    @property
    def chave(self) -> tuple[int, str]:
        return Combinacao(self.modmask, self.key).chave_conflito


@dataclass(frozen=True)
class UnbindFonte:
    modmask: int
    key: str
    arquivo: str


def interpretar(saida: str) -> tuple[list[BindFonte], list[UnbindFonte]]:
    binds: list[BindFonte] = []
    unbinds: list[UnbindFonte] = []
    for linha in saida.splitlines():
        campos = linha.split("\t")
        if campos[0] == "BIND" and len(campos) >= 7:
            binds.append(BindFonte(int(campos[1] or 0), campos[2], campos[3], campos[4], campos[5], campos[6]))
        elif campos[0] == "UNBIND" and len(campos) >= 4:
            unbinds.append(UnbindFonte(int(campos[1] or 0), campos[2], campos[3]))
    return binds, unbinds


def varrer(hyprland_lua: Path | None = None, executar_fn=executar) -> tuple[list[BindFonte], list[UnbindFonte]]:
    import os

    config = hyprland_lua or (caminhos.HYPR_DIR / "hyprland.lua")
    if not config.is_file():
        return [], []
    env = dict(os.environ)
    env["OMGR_HYPRLAND_LUA"] = str(config)
    env.setdefault("OMARCHY_PATH", str(caminhos.omarchy_path()))
    try:
        r = executar_fn(["lua", "-E", str(STUB)], timeout=15, env=env)
    except ComandoAusente:
        logger.warning("lua ausente, binds ficam sem comando e sem origem")
        return [], []
    if not r.ok:
        logger.warning("varredura Lua falhou (rc=%s): %s", r.codigo, r.stderr.strip()[:300])
    return interpretar(r.stdout)


def classificar_origem(arquivo: str, pastas_plugins: dict[str, Path] | None = None) -> tuple[Origem, str]:
    """Devolve (origem, plugin_id) a partir do caminho do arquivo Lua."""
    if not arquivo:
        return "desconhecida", ""
    caminho = Path(arquivo)
    try:
        resolvido = caminho.resolve()
    except OSError:
        resolvido = caminho
    if resolvido == caminhos.HYPR_MANAGER_BINDINGS.resolve():
        return "gerenciador", ""
    for pid, pasta in (pastas_plugins or {}).items():
        try:
            resolvido.relative_to(pasta.resolve())
            return "plugin", pid
        except (ValueError, OSError):
            continue
    for raiz in (caminhos.omarchy_path(), Path("/usr/share/omarchy")):
        try:
            resolvido.relative_to(raiz.resolve())
            return "omarchy", ""
        except (ValueError, OSError):
            continue
    try:
        resolvido.relative_to(Path.home().resolve())
        return "usuario", ""
    except ValueError:
        return "desconhecida", ""


def atalhos_completos(hyprland, pastas_plugins: dict[str, Path] | None = None, executar_fn=executar) -> list[Atalho]:
    """`hyprctl binds -j` + varredura Lua, já com comando e origem."""
    atalhos = hyprland.atalhos()
    binds, _ = varrer(executar_fn=executar_fn)
    return enriquecer(atalhos, binds, pastas_plugins)


def enriquecer(atalhos: list[Atalho], binds: list[BindFonte], pastas_plugins: dict[str, Path] | None = None) -> list[Atalho]:
    """Casa cada atalho do hyprctl com a fonte Lua por (modmask, descrição) e,
    em empate, pela tecla. Preenche comando, arquivo, origem e plugin."""
    por_desc: dict[tuple[int, str], list[BindFonte]] = {}
    for b in binds:
        por_desc.setdefault((b.modmask, b.description), []).append(b)
    saida: list[Atalho] = []
    for a in atalhos:
        candidatos = por_desc.get((a.modmask, a.description), [])
        fonte = None
        if len(candidatos) == 1:
            fonte = candidatos[0]
        elif candidatos:
            chave = Combinacao(a.modmask, a.key, a.keycode).chave_conflito
            fonte = next((c for c in candidatos if c.chave == chave), candidatos[0])
        if fonte is None:
            saida.append(a)
            continue
        origem, plugin_id = classificar_origem(fonte.arquivo, pastas_plugins)
        key = a.key or fonte.key
        saida.append(
            Atalho(
                **{
                    **a.__dict__,
                    "key": key,
                    "comando": fonte.comando if fonte.kind in ("exec", "lua") else a.comando,
                    "dispatcher": "exec" if fonte.kind == "exec" and a.dispatcher == "__lua" else a.dispatcher,
                    "arquivo": fonte.arquivo,
                    "origem": origem,
                    "plugin_id": plugin_id,
                }
            )
        )
    return saida
