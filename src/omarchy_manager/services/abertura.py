"""Abertura: marcador de "já mostrei neste boot" e a opção na config do app.

O marcador mora em $XDG_RUNTIME_DIR/omarchy-manager/ (tmpfs, some ao desligar).
Ausente, ilegível ou corrompido vale como "ainda não mostrei". Sem dado sensível.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

from omarchy_manager.services import arquivos, caminhos

NOME_MARCADOR = "abertura-mostrada"
CONTEUDO = "1\n"


def pasta_estado() -> Path | None:
    base = os.environ.get("XDG_RUNTIME_DIR")
    if not base or not os.path.isdir(base):
        return None
    return Path(base) / "omarchy-manager"


def ja_mostrou() -> bool:
    pasta = pasta_estado()
    if pasta is None:
        return False
    try:
        return (pasta / NOME_MARCADOR).read_text(errors="replace").strip() == "1"
    except OSError:
        return False


def marcar() -> None:
    pasta = pasta_estado()
    if pasta is None:
        return
    try:
        pasta.mkdir(parents=True, exist_ok=True)
        os.chmod(pasta, 0o700)
        (pasta / NOME_MARCADOR).write_text(CONTEUDO)
    except OSError:
        pass


def deve_mostrar() -> bool:
    return abertura_ativa() and not ja_mostrou()


def abertura_ativa(arquivo: Path | None = None) -> bool:
    """Opção da aba Config ([abertura] mostrar); sem escolha, ligada."""
    try:
        with open(arquivo or caminhos.CONFIG_TOML, "rb") as fh:
            valor = tomllib.load(fh).get("abertura", {}).get("mostrar")
    except (OSError, tomllib.TOMLDecodeError, AttributeError):
        valor = None
    return valor if isinstance(valor, bool) else True


def definir_abertura_ativa(ativa: bool, arquivo: Path | None = None) -> None:
    from omarchy_manager.services.temas import _chave_toml, _valor_toml

    arq = caminhos.garantir_gravavel(arquivo or caminhos.CONFIG_TOML)
    try:
        with open(arq, "rb") as fh:
            dados = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        dados = {}
    sec = dados.get("abertura")
    sec = dict(sec) if isinstance(sec, dict) else {}
    sec["mostrar"] = bool(ativa)
    dados["abertura"] = sec
    linhas = ["# Gerado por omarchy-manager. Edite à vontade; chaves desconhecidas são preservadas.", ""]
    for k, v in dados.items():
        if not isinstance(v, dict):
            linhas.append(f"{_chave_toml(k)} = {_valor_toml(v)}")
    for k, v in dados.items():
        if isinstance(v, dict):
            linhas += ["", f"[{k}]"]
            linhas += [f"{_chave_toml(a)} = {_valor_toml(b)}" for a, b in v.items()]
    texto = "\n".join(linhas) + "\n"
    tomllib.loads(texto)
    arquivos.gravar(arq, texto)
