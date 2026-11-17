"""Configurações do terminal padrão (por ora só Foot): opacidade, fonte, margem, cursor.

Tudo é escrito no `~/.config/foot/foot.ini` do usuário, nunca nos arquivos do
Omarchy. O Foot lê `include=` na seção [main], no topo, e o último valor lido
vence; por isso o `alpha` é gravado em [colors-dark] e [colors-light] no fim
do arquivo, onde ganha do `alpha` que o tema ou o toggle de transparência
puseram. O Foot não recarrega a configuração com janelas abertas: opacidade
vale na hora só para este terminal (OSC 11), o resto vale para janelas novas.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, replace
from pathlib import Path

from omarchy_manager.services import arquivos, terminal_foot
from omarchy_manager.services.executor import ComandoAusente, executar

CURSORES = ("block", "beam", "underline")


@dataclass(frozen=True)
class ConfigTerminal:
    opacidade: int = 100  # 0 a 100, em porcentagem
    fonte: str = ""
    tamanho: float = 10.0
    margem: int = 0  # pixels, igual nos dois eixos
    cursor: str = "block"
    piscar: bool = False
    historico: int = 10000  # linhas de rolagem


def arquivo_foot() -> Path:
    return terminal_foot._config_do_foot()


def terminal_padrao() -> str:
    """Nome do terminal padrão do Omarchy (`omarchy-default-terminal`), ou vazio."""
    try:
        r = executar(["omarchy-default-terminal"], timeout=5)
    except ComandoAusente:
        return ""
    return r.stdout.strip().lower() if r.ok else ""


# Edição de INI preservando comentários e a ordem do arquivo

_SECAO = re.compile(r"^\s*\[([^\]]+)\]\s*$")


def _chave_da_linha(linha: str) -> str | None:
    s = linha.strip()
    if not s or s.startswith(("#", ";", "[")) or "=" not in s:
        return None
    return s.split("=", 1)[0].strip().lower()


def ler_ini(texto: str, secao: str, chave: str) -> str | None:
    """Último valor de `chave` em `[secao]` neste texto (sem seguir include)."""
    atual, achado = "main", None
    for linha in texto.splitlines():
        m = _SECAO.match(linha)
        if m:
            atual = m.group(1).strip().lower()
        elif atual == secao and _chave_da_linha(linha) == chave:
            achado = linha.split("=", 1)[1].split(" #")[0].strip()
    return achado


def definir_ini(texto: str, secao: str, chave: str, valor: str) -> str:
    """Troca `chave=valor` em `[secao]`, cria a chave ou a seção se faltar."""
    linhas = texto.splitlines()
    atual = "main"
    ultima_na_secao = fim_secao = None
    inicio_secao = None
    for i, linha in enumerate(linhas):
        m = _SECAO.match(linha)
        if m:
            if atual == secao and fim_secao is None:
                fim_secao = i
            atual = m.group(1).strip().lower()
            if atual == secao and inicio_secao is None:
                inicio_secao = i
            continue
        if atual == secao and _chave_da_linha(linha) == chave:
            ultima_na_secao = i
    nova = f"{chave}={valor}"
    if ultima_na_secao is not None:
        linhas[ultima_na_secao] = nova
    elif inicio_secao is not None:
        fim = fim_secao if fim_secao is not None else len(linhas)
        while fim > inicio_secao + 1 and not linhas[fim - 1].strip():
            fim -= 1
        linhas.insert(fim, nova)
    else:
        if linhas and linhas[-1].strip():
            linhas.append("")
        linhas += [f"[{secao}]", nova]
    return "\n".join(linhas) + "\n"


def _fonte_e_tamanho(valor: str | None) -> tuple[str, float | None]:
    if not valor:
        return "", None
    nome, _, resto = valor.partition(":")
    m = re.search(r"size=([0-9.]+)", resto)
    return nome.strip(), float(m.group(1)) if m else None


def ler(arquivo: Path | None = None) -> ConfigTerminal:
    arq = arquivo or arquivo_foot()
    try:
        texto = arq.read_text(encoding="utf-8")
    except OSError:
        texto = ""
    padrao = ConfigTerminal()
    nome, tam = _fonte_e_tamanho(ler_ini(texto, "main", "font"))
    margem = re.match(r"\s*(\d+)", ler_ini(texto, "main", "pad") or "")
    hist = ler_ini(texto, "scrollback", "lines") or ""
    alphas = terminal_foot.ler_alphas(arq)
    alpha = alphas.get("colors-dark", alphas.get("colors", 1.0))
    cursor = (ler_ini(texto, "cursor", "style") or padrao.cursor).lower()
    return ConfigTerminal(
        opacidade=round(alpha * 100),
        fonte=nome or padrao.fonte,
        tamanho=tam or padrao.tamanho,
        margem=int(margem.group(1)) if margem else padrao.margem,
        cursor=cursor if cursor in CURSORES else padrao.cursor,
        piscar=(ler_ini(texto, "cursor", "blink") or "no").lower() in ("yes", "true", "on", "1"),
        historico=int(hist) if hist.isdigit() else padrao.historico,
    )


def validar(cfg: ConfigTerminal) -> ConfigTerminal:
    """Limita cada valor a uma faixa que o Foot aceita e que não deixa o terminal ilegível."""
    nome = re.sub(r"[\r\n:=]", "", cfg.fonte).strip()
    return replace(
        cfg,
        opacidade=min(100, max(10, int(cfg.opacidade))),
        fonte=nome,
        tamanho=min(48.0, max(4.0, float(cfg.tamanho))),
        margem=min(100, max(0, int(cfg.margem))),
        cursor=cfg.cursor if cfg.cursor in CURSORES else "block",
        historico=min(1_000_000, max(0, int(cfg.historico))),
    )


def _fmt_tamanho(t: float) -> str:
    return str(int(t)) if float(t).is_integer() else f"{t:g}"


def gerar_texto(texto: str, cfg: ConfigTerminal) -> str:
    cfg = validar(cfg)
    if cfg.fonte:
        texto = definir_ini(texto, "main", "font", f"{cfg.fonte}:size={_fmt_tamanho(cfg.tamanho)}")
    texto = definir_ini(texto, "main", "pad", f"{cfg.margem}x{cfg.margem}")
    texto = definir_ini(texto, "cursor", "style", cfg.cursor)
    texto = definir_ini(texto, "cursor", "blink", "yes" if cfg.piscar else "no")
    texto = definir_ini(texto, "scrollback", "lines", str(cfg.historico))
    alpha = f"{cfg.opacidade / 100:.2f}".rstrip("0").rstrip(".") if cfg.opacidade < 100 else "1"
    for secao in ("colors-dark", "colors-light"):
        texto = definir_ini(texto, secao, "alpha", alpha)
    return texto


def gravar(cfg: ConfigTerminal, arquivo: Path | None = None) -> Path | None:
    """Grava no foot.ini do usuário, com backup. Devolve o backup (ou None se o arquivo era novo)."""
    arq = arquivo or arquivo_foot()
    try:
        texto = arq.read_text(encoding="utf-8")
    except OSError:
        texto = ""
    return arquivos.gravar(arq, gerar_texto(texto, cfg))


def foot_instalado() -> bool:
    return shutil.which("foot") is not None or arquivo_foot().exists()
