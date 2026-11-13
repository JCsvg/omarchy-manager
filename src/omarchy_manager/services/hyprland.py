"""HyprlandService: atalhos efetivos, conflitos, reload e configerrors."""

from __future__ import annotations

import json
import re
from collections import Counter

from omarchy_manager.models import Atalho
from omarchy_manager.services.executor import ComandoAusente, Resultado, executar
from omarchy_manager.services.log import logger
from omarchy_manager.services.teclas import Combinacao, conflitam


class ErroHyprland(RuntimeError):
    pass


def atalhos_de_json(texto: str) -> list[Atalho]:
    dados = json.loads(texto or "[]")
    atalhos = []
    for b in dados:
        atalhos.append(
            Atalho(
                modmask=int(b.get("modmask", 0)),
                key=str(b.get("key", "")),
                keycode=int(b.get("keycode", 0) or 0),
                description=str(b.get("description", "")),
                dispatcher=str(b.get("dispatcher", "")),
                arg=str(b.get("arg", "")),
                submap=str(b.get("submap", "")),
            )
        )
    return atalhos


_CAMPO = re.compile(r"^\t([a-z_]+): (.*)$")


def atalhos_de_texto(texto: str) -> list[Atalho]:
    """Fallback para o `hyprctl binds` sem -j (0.56.0 emitia JSON inválido)."""
    atalhos: list[Atalho] = []
    campos: dict[str, str] = {}

    def fechar() -> None:
        if campos:
            atalhos.append(
                Atalho(
                    modmask=int(campos.get("modmask", "0") or 0),
                    key=campos.get("key", ""),
                    keycode=int(campos.get("keycode", "0") or 0),
                    description=campos.get("description", ""),
                    dispatcher=campos.get("dispatcher", ""),
                    arg=campos.get("arg", ""),
                    submap=campos.get("submap", ""),
                )
            )

    for linha in texto.splitlines():
        if linha.startswith("bind"):
            fechar()
            campos = {}
            continue
        m = _CAMPO.match(linha)
        if m:
            campos[m.group(1)] = m.group(2)
    fechar()
    return atalhos


def marcar_duplicados(atalhos: list[Atalho]) -> list[Atalho]:
    chaves = Counter(Combinacao(a.modmask, a.key, a.keycode).chave_conflito for a in atalhos if not a.submap)
    saida = []
    for a in atalhos:
        chave = Combinacao(a.modmask, a.key, a.keycode).chave_conflito
        dup = not a.submap and chaves[chave] > 1
        saida.append(a if a.duplicado == dup else Atalho(**{**a.__dict__, "duplicado": dup}))
    return saida


class HyprlandService:
    def __init__(self, executar_fn=executar) -> None:
        self._executar = executar_fn

    def _rodar(self, *args: str, timeout: float = 15.0) -> Resultado:
        try:
            return self._executar(["hyprctl", *args], timeout=timeout)
        except ComandoAusente as exc:
            raise ErroHyprland("`hyprctl` não está instalado") from exc

    def atalhos(self) -> list[Atalho]:
        r = self._rodar("binds", "-j")
        if r.ok:
            try:
                return marcar_duplicados(atalhos_de_json(r.stdout))
            except (json.JSONDecodeError, ValueError):
                logger.warning("hyprctl binds -j devolveu JSON inválido, usando a saída textual")
        r = self._rodar("binds")
        if not r.ok:
            raise ErroHyprland(f"`hyprctl binds` falhou: {r.erro_legivel}")
        return marcar_duplicados(atalhos_de_texto(r.stdout))

    def usos(self, combinacao: Combinacao, atalhos: list[Atalho] | None = None) -> list[Atalho]:
        """Atalhos já ligados à combinação, fora de submaps."""
        lista = atalhos if atalhos is not None else self.atalhos()
        return [a for a in lista if not a.submap and conflitam(combinacao, Combinacao(a.modmask, a.key, a.keycode))]

    def reload(self) -> Resultado:
        logger.info("hyprctl reload")
        return self._rodar("reload", timeout=30)

    def configerrors(self) -> list[str]:
        r = self._rodar("configerrors")
        if not r.ok:
            raise ErroHyprland(f"`hyprctl configerrors` falhou: {r.erro_legivel}")
        return [linha for linha in r.stdout.splitlines() if linha.strip()]

    def eval_lua(self, expressao: str, timeout: float = 10.0) -> Resultado:
        """`hyprctl eval` roda Lua dentro do compositor. Só código nosso, nunca
        texto vindo de arquivo ou de rede."""
        return self._rodar("eval", expressao, timeout=timeout)
