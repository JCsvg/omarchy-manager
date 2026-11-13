"""Mantém a transparência do Foot depois de uma troca de tema.

Causa do defeito: `omarchy theme set` chama `omarchy-theme-set-foot`, que
escreve em todo Foot aberto um `OSC 11;[alpha]cor`. O alpha vem só do
`foot.ini` do tema; quando o tema não define alpha, vai `[100]`, opaco, e o
`alpha` que o usuário pôs em `~/.config/foot/foot.ini` é ignorado. A janela
só volta a ficar transparente quando outro Foot é aberto.

Correção do nosso lado: depois de recarregar a paleta, reenviar o mesmo OSC 11
para o nosso terminal com o alpha do `foot.ini` do usuário. Só quando o
terminal se identifica como Foot e há um alpha menor que 1 configurado.
"""

from __future__ import annotations

import os
from pathlib import Path

from omarchy_manager.services import terminal_grafico


def _config_do_foot() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "foot" / "foot.ini"


def ler_alphas(arquivo: Path, _vistos: set[Path] | None = None) -> dict[str, float]:
    """`alpha` por seção ([colors], [colors-dark], [colors-light]), seguindo `include=`.
    Como no Foot, o último valor lido de cada seção vence."""
    vistos = _vistos if _vistos is not None else set()
    alphas: dict[str, float] = {}
    try:
        caminho = arquivo.expanduser().resolve()
        if caminho in vistos or len(vistos) > 16:
            return alphas
        vistos.add(caminho)
        linhas = caminho.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return alphas
    secao = "main"
    for bruta in linhas:
        linha = bruta.split("#", 1)[0].strip() if not bruta.strip().startswith("#") else ""
        if not linha:
            continue
        if linha.startswith("[") and linha.endswith("]"):
            secao = linha[1:-1].strip().lower()
            continue
        chave, _, valor = linha.partition("=")
        chave, valor = chave.strip().lower(), valor.strip()
        if chave == "include" and valor:
            alphas.update(ler_alphas(Path(valor), vistos))
        elif chave == "alpha" and secao.startswith("colors"):
            try:
                alphas[secao] = min(1.0, max(0.0, float(valor)))
            except ValueError:
                pass
    return alphas


def alpha_do_usuario(escuro: bool, arquivo: Path | None = None) -> float | None:
    alphas = ler_alphas(arquivo or _config_do_foot())
    for secao in ("colors-dark" if escuro else "colors-light", "colors"):
        if secao in alphas:
            return alphas[secao]
    return None


def eh_foot() -> bool:
    nome = terminal_grafico.capacidades().nome.lower()
    if nome:
        return nome.startswith("foot")
    return os.environ.get("TERM", "").startswith("foot")


def sequencia_alpha(fundo: str, escuro: bool, arquivo: Path | None = None) -> str:
    """O OSC 11 que devolve ao Foot o alpha do usuário, ou "" se não há o que fazer."""
    if not eh_foot() or not (fundo.startswith("#") and len(fundo) == 7):
        return ""
    alpha = alpha_do_usuario(escuro, arquivo)
    if alpha is None or alpha >= 1.0:
        return ""
    return f"\x1b]11;[{int(alpha * 100 + 0.5)}]{fundo}\x07"
