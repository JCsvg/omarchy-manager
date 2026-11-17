"""Prompt powerline do app, feito com Oh My Posh (tema no estilo M365Princess).

O tema fica em `~/.config/omarchy-manager/` e o `~/.bashrc` ganha um bloco
entre marcadores que só carrega o oh-my-posh se o binário existir. Ligar e
desligar só mexe nesse bloco; o resto do arquivo não é tocado. Cada gravação
faz backup do bashrc. Não mexe em nada do Omarchy. Precisa de Nerd Font.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from omarchy_manager.services import arquivos, caminhos

INICIO = "# >>> omarchy-manager prompt (oh-my-posh) >>>"
FIM = "# <<< omarchy-manager prompt (oh-my-posh) <<<"

SEG = ""  # seta powerline


def _seg(tipo, fundo, texto, template, props=None, fg="#ffffff"):
    return {
        "type": tipo, "style": "diamond" if tipo == "session" else "powerline",
        "powerline_symbol": SEG, "foreground": fg, "background": fundo,
        "template": template, **({"properties": props} if props else {}),
        **({"leading_diamond": ""} if tipo == "session" else {}),
    }


TEMA = {
    "$schema": "https://raw.githubusercontent.com/JanDeDobbeleer/oh-my-posh/main/themes/schema.json",
    "version": 3,
    "final_space": True,
    "blocks": [{
        "type": "prompt", "alignment": "left",
        "segments": [
            _seg("session", "#6f8fe0", "", " {{ .UserName }} "),
            _seg("path", "#f0508f", "", "  {{ .Path }} ",
                 {"style": "folder", "max_depth": 3}),
            _seg("git", "#f5d03b", "", " {{ .HEAD }}{{ if .Working.Changed }}  {{ .Working.String }}{{ end }}{{ if gt .Ahead 0 }} ⇡{{ .Ahead }}{{ end }}{{ if gt .Behind 0 }} ⇣{{ .Behind }}{{ end }} ",
                 {"fetch_status": True, "branch_icon": " "}, fg="#1e1e2e"),
            _seg("dotnet", "#6fcf7f", "", "  {{ .Full }} ", fg="#1e1e2e"),
            _seg("executiontime", "#a56bd6", "", " {{ .FormattedMs }} ",
                 {"threshold": 2000, "style": "round"}),
            _seg("time", "#4a5a8a", "", " {{ .CurrentDate | date \"15:04\" }} ",
                 {"time_format": "15:04"}),
        ],
    }],
}
# o diamante de abertura do user usa a cor do próprio segmento
TEMA["blocks"][0]["segments"][0]["style"] = "powerline"
TEMA["blocks"][0]["segments"][0].pop("leading_diamond", None)


def arquivo_tema() -> Path:
    return caminhos.CONFIG_DIR / "posh-m365princess.omp.json"


def arquivo_bashrc() -> Path:
    return Path.home() / ".bashrc"


def binario() -> str | None:
    achado = shutil.which("oh-my-posh")
    if achado:
        return achado
    local = Path.home() / ".local" / "bin" / "oh-my-posh"
    return str(local) if os.access(local, os.X_OK) else None


def gerar_tema() -> str:
    return json.dumps(TEMA, indent=2, ensure_ascii=False) + "\n"


def bloco(tema: Path) -> str:
    return (
        f"{INICIO}\n"
        'export PATH="$HOME/.local/bin:$PATH"\n'
        'if command -v oh-my-posh >/dev/null 2>&1; then\n'
        f'  eval "$(oh-my-posh init bash --config \'{tema}\')"\n'
        "fi\n"
        f"{FIM}\n"
    )


def _sem_bloco(texto: str) -> str:
    if INICIO not in texto or FIM not in texto:
        return texto
    antes, resto = texto.split(INICIO, 1)
    _, depois = resto.split(FIM, 1)
    return (antes.rstrip("\n") + "\n" + depois.lstrip("\n")).lstrip("\n") if antes.strip() else depois.lstrip("\n")


def ativo(bashrc: Path | None = None) -> bool:
    try:
        return INICIO in (bashrc or arquivo_bashrc()).read_text(encoding="utf-8")
    except OSError:
        return False


def ativar(bashrc: Path | None = None, tema: Path | None = None) -> tuple[bool, str]:
    if binario() is None:
        return False, "o oh-my-posh não está instalado (esperado em ~/.local/bin), nada foi alterado"
    tema = tema or arquivo_tema()
    tema.parent.mkdir(parents=True, exist_ok=True)
    tema.write_text(gerar_tema(), encoding="utf-8")
    rc = bashrc or arquivo_bashrc()
    try:
        atual = rc.read_text(encoding="utf-8")
    except OSError:
        atual = ""
    limpo = _sem_bloco(atual)
    novo = (limpo.rstrip("\n") + "\n\n" if limpo.strip() else "") + bloco(tema)
    if novo == atual:
        return True, "Prompt powerline já estava ligado."
    backup = arquivos.gravar(rc, novo)
    onde = f"backup em {backup}" if backup else "bashrc novo"
    return True, f"Prompt powerline ligado ({onde}). Vale para terminais novos."


def desativar(bashrc: Path | None = None) -> tuple[bool, str]:
    rc = bashrc or arquivo_bashrc()
    try:
        atual = rc.read_text(encoding="utf-8")
    except OSError:
        atual = ""
    if INICIO not in atual:
        return False, "o prompt powerline não está ligado no bashrc"
    backup = arquivos.gravar(rc, _sem_bloco(atual))
    return True, f"Prompt powerline desligado (backup em {backup}). O tema continua guardado."
