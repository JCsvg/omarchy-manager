"""Escrita segura dos atalhos gerenciados (plano 6.4).

O gerenciador só escreve em `~/.config/hypr/omarchy-manager-bindings.lua`,
gerado de forma determinística a partir de uma lista de overrides guardada
no cabeçalho do próprio arquivo (JSON em comentário). No `bindings.lua` do
usuário entra uma única linha de carregamento, idempotente.

Cada gravação: arquivo temporário no mesmo diretório, validação sintática
com `lua`, backup com data e hora, troca atômica, retenção de 20 backups,
`hyprctl reload` + `hyprctl configerrors` e restauração automática se houver
erro.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from omarchy_manager.services import caminhos
from omarchy_manager.services.executor import ComandoAusente, executar
from omarchy_manager.services.hyprland import HyprlandService
from omarchy_manager.services.log import logger
from omarchy_manager.services.teclas import normalizar

VERSAO_ESTADO = 1
MARCADOR_ESTADO = "-- omarchy-manager:state "
MARCADOR_LOADER = "-- omarchy-manager: carrega os atalhos gerenciados"
LINHA_LOADER = (
    MARCADOR_LOADER
    + "\n"
    + 'do local p = (os.getenv("XDG_CONFIG_HOME") or (os.getenv("HOME") .. "/.config")) .. "/hypr/omarchy-manager-bindings.lua"'
    + " local f = io.open(p) if f then f:close() dofile(p) end end\n"
)
RETENCAO_BACKUPS = 20
_EXPRESSAO_LUA = re.compile(r"^hl\.dsp\.[A-Za-z_][A-Za-z0-9_.]*\([^\n\r]*\)$")

Tipo = Literal["bind", "unbind"]


class ErroOverrides(RuntimeError):
    pass


class ErroAplicacao(ErroOverrides):
    def __init__(self, erros: list[str], restaurado: bool) -> None:
        super().__init__("; ".join(erros) or "erro de configuração do Hyprland")
        self.erros = erros
        self.restaurado = restaurado


@dataclass(frozen=True)
class Override:
    tipo: Tipo
    combinacao: str
    descricao: str = ""
    comando: str = ""
    kind: str = "exec"  # exec | lua

    @property
    def chave(self) -> tuple[str, str]:
        return (self.tipo, normalizar(self.combinacao).canonica)


def lua_string(texto: str) -> str:
    if any(ord(c) < 32 and c not in "\t" for c in texto):
        raise ErroOverrides(f"texto com caractere de controle: {texto!r}")
    return '"' + texto.replace("\\", "\\\\").replace('"', '\\"').replace("\t", "\\t") + '"'


def _validar(o: Override) -> Override:
    canonica = normalizar(o.combinacao).canonica
    if o.tipo == "unbind":
        return Override("unbind", canonica)
    if o.kind == "lua":
        if not _EXPRESSAO_LUA.match(o.comando):
            raise ErroOverrides(f"expressão Lua não reconhecida: {o.comando!r}")
    elif o.kind == "exec":
        if not o.comando.strip():
            raise ErroOverrides("comando vazio")
        if "\n" in o.comando or "\r" in o.comando:
            raise ErroOverrides("comando com quebra de linha")
    else:
        raise ErroOverrides(f"tipo de dispatcher desconhecido: {o.kind}")
    return Override("bind", canonica, o.descricao.strip(), o.comando.strip(), o.kind)


def gerar_lua(overrides: list[Override]) -> str:
    """Saída determinística: mesma lista (em qualquer ordem) -> mesmo texto."""
    validos = [_validar(o) for o in overrides]
    unicos: dict[tuple[str, str], Override] = {}
    for o in validos:
        unicos[o.chave] = o
    ordenados = sorted(unicos.values(), key=lambda o: (o.tipo != "unbind", o.combinacao))
    estado = json.dumps(
        {"versao": VERSAO_ESTADO, "overrides": [asdict(o) for o in ordenados]}, ensure_ascii=False, sort_keys=True
    )
    linhas = [
        "-- Gerado pelo omarchy-manager. Não edite à mão: a próxima gravação sobrescreve.",
        "-- Para desfazer, use o botão 'Desfazer última alteração' ou apague este arquivo.",
        MARCADOR_ESTADO + estado,
        "",
    ]
    for o in ordenados:
        if o.tipo == "unbind":
            linhas.append(f"-- Desligado pelo gerenciador: {o.combinacao}")
            linhas.append(f"hl.unbind({lua_string(o.combinacao)})")
        else:
            linhas.append(f"-- {o.descricao or '(sem descrição)'}")
            linhas.append(f"hl.unbind({lua_string(o.combinacao)})")
            if o.kind == "exec":
                linhas.append(
                    f"o.bind({lua_string(o.combinacao)}, {lua_string(o.descricao) if o.descricao else 'nil'}, {lua_string(o.comando)})"
                )
            else:
                desc = f"{{ description = {lua_string(o.descricao)} }}" if o.descricao else "{}"
                linhas.append(f"hl.bind({lua_string(o.combinacao)}, {o.comando}, {desc})")
        linhas.append("")
    return "\n".join(linhas)


def ler_overrides(texto: str) -> list[Override]:
    for linha in texto.splitlines():
        if linha.startswith(MARCADOR_ESTADO):
            try:
                dados = json.loads(linha[len(MARCADOR_ESTADO) :])
            except json.JSONDecodeError as exc:
                raise ErroOverrides("estado do arquivo gerenciado está corrompido") from exc
            return [Override(**o) for o in dados.get("overrides", [])]
    return []


class GerenciadorOverrides:
    def __init__(
        self,
        hyprland: HyprlandService | None = None,
        arquivo: Path | None = None,
        bindings_usuario: Path | None = None,
        pasta_backups: Path | None = None,
        executar_fn=executar,
    ) -> None:
        self.hyprland = hyprland or HyprlandService()
        self.arquivo = arquivo or caminhos.HYPR_MANAGER_BINDINGS
        self.bindings_usuario = bindings_usuario or caminhos.HYPR_BINDINGS
        self.pasta_backups = pasta_backups or caminhos.BACKUPS_DIR
        self._executar = executar_fn

    # Leitura

    def atuais(self) -> list[Override]:
        try:
            return ler_overrides(self.arquivo.read_text(encoding="utf-8"))
        except OSError:
            return []

    # Backups

    def _backup(self, origem: Path, rotulo: str) -> Path | None:
        if not origem.is_file():
            return None
        self.pasta_backups.mkdir(parents=True, exist_ok=True)
        carimbo = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        destino = self.pasta_backups / f"{rotulo}.{carimbo}.lua"
        shutil.copy2(origem, destino)
        self._podar(rotulo)
        logger.info("backup %s -> %s", origem, destino)
        return destino

    def _podar(self, rotulo: str) -> None:
        backups = sorted(self.pasta_backups.glob(f"{rotulo}.*.lua"))
        for velho in backups[:-RETENCAO_BACKUPS]:
            try:
                velho.unlink()
            except OSError:
                pass

    def backups(self) -> list[Path]:
        return sorted(self.pasta_backups.glob("omarchy-manager-bindings.*.lua"), reverse=True)

    # Escrita

    def _validar_sintaxe(self, arquivo: Path) -> None:
        try:
            # loadfile compila sem executar: `hl` e `o` só existem no compositor.
            r = self._executar(["lua", "-E", "-e", f"assert(loadfile({lua_string(str(arquivo))}))"], timeout=10)
        except ComandoAusente:
            logger.warning("lua ausente, validação sintática pulada")
            return
        if not r.ok:
            raise ErroOverrides(f"Lua gerado inválido: {r.erro_legivel}")

    def _escrever_atomico(self, destino: Path, conteudo: str) -> None:
        destino = caminhos.garantir_gravavel(destino)
        destino.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=destino.parent, prefix=f".{destino.name}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(conteudo)
            self._validar_sintaxe(Path(tmp))
            os.replace(tmp, destino)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def garantir_loader(self) -> bool:
        """Acrescenta a linha de carregamento ao bindings.lua do usuário, 1 vez."""
        atual = ""
        if self.bindings_usuario.is_file():
            atual = self.bindings_usuario.read_text(encoding="utf-8")
            if MARCADOR_LOADER in atual:
                return False
        self._backup(self.bindings_usuario, "bindings")
        novo = atual + ("" if atual.endswith("\n") or not atual else "\n") + "\n" + LINHA_LOADER
        self._escrever_atomico(self.bindings_usuario, novo)
        logger.info("linha de carregamento adicionada a %s", self.bindings_usuario)
        return True

    def _recarregar_e_verificar(self) -> list[str]:
        r = self.hyprland.reload()
        if not r.ok:
            return [f"hyprctl reload falhou: {r.erro_legivel}"]
        return self.hyprland.configerrors()

    def aplicar(self, overrides: list[Override]) -> Path | None:
        """Grava, recarrega e verifica. Se o Hyprland acusar erro, restaura o
        backup, recarrega de novo e levanta ErroAplicacao."""
        conteudo = gerar_lua(overrides)
        backup = self._backup(self.arquivo, "omarchy-manager-bindings")
        existia = self.arquivo.is_file()
        self._escrever_atomico(self.arquivo, conteudo)
        self.garantir_loader()
        erros = self._recarregar_e_verificar()
        if not erros:
            logger.info("overrides aplicados: %d entradas", len(overrides))
            return backup
        logger.warning("configerrors após gravar, restaurando: %s", erros)
        restaurado = self._restaurar(backup, existia)
        erros_depois = self._recarregar_e_verificar()
        if erros_depois:
            logger.error("erros persistem após restaurar: %s", erros_depois)
        raise ErroAplicacao(erros, restaurado and not erros_depois)

    def _restaurar(self, backup: Path | None, existia: bool) -> bool:
        try:
            if backup is not None and backup.is_file():
                shutil.copy2(backup, caminhos.garantir_gravavel(self.arquivo))
            elif not existia:
                caminhos.garantir_gravavel(self.arquivo).unlink(missing_ok=True)
            else:
                return False
            return True
        except OSError as exc:
            logger.error("falha ao restaurar %s: %s", self.arquivo, exc)
            return False

    def desfazer(self) -> Path | None:
        """Volta ao backup mais recente do arquivo gerenciado e o consome."""
        lista = self.backups()
        if not lista:
            raise ErroOverrides("não há backup para desfazer")
        ultimo = lista[0]
        shutil.copy2(ultimo, caminhos.garantir_gravavel(self.arquivo))
        erros = self._recarregar_e_verificar()
        if erros:
            raise ErroAplicacao(erros, False)
        ultimo.unlink(missing_ok=True)
        logger.info("desfeito com %s", ultimo)
        return ultimo
