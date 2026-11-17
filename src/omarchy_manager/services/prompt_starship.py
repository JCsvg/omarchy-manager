"""Prompt do Starship em "pílulas" coloridas (diretório, git, .NET, bateria, hora).

O preset é gravado em `~/.config/starship.toml` com backup, depois de passar
por `starship prompt` num arquivo temporário: se o Starship rejeitar, nada é
trocado. Precisa de uma fonte Nerd Font no terminal (o Omarchy já traz).
As cores são fixas, não acompanham o tema do Omarchy.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from omarchy_manager.services import arquivos
from omarchy_manager.services.executor import ComandoAusente, executar

CAP_E = "\ue0b6"
CAP_D = "\ue0b4"

ROSA = "#f0508f"
AMARELO = "#f5d03b"
VERDE = "#6fcf7f"
ROXO = "#a56bd6"


def _pilula(cor: str, texto: str, fg: str = "#1e1e2e") -> str:
    return f"[{CAP_E}](fg:{cor})[{texto}](bg:{cor} fg:{fg})[{CAP_D}](fg:{cor}) "


PRESET_POWERLINE = f"""# Gerado pelo omarchy-manager (preset powerline). Desfaça pela aba Terminal.
add_newline = true
command_timeout = 500
format = "$directory$git_branch$git_status$dotnet$character"
right_format = "$battery$time"

[character]
success_symbol = "[❯](bold fg:{VERDE})"
error_symbol = "[✗](bold fg:{ROSA})"

[directory]
truncation_length = 3
truncation_symbol = "…/"
format = '{_pilula(ROSA, " \uf07b $path ")}'

[git_branch]
format = '[{CAP_E}](fg:{AMARELO})[ \ue0a0 $branch ](bg:{AMARELO} fg:#1e1e2e)'

[git_status]
format = '[($all_status$ahead_behind )](bg:{AMARELO} fg:#1e1e2e)[{CAP_D}](fg:{AMARELO}) '
ahead = "⇡${{count}}"
behind = "⇣${{count}}"
diverged = "⇕⇡${{ahead_count}}⇣${{behind_count}}"
untracked = "?"
modified = "!"
staged = "+"

[dotnet]
format = '{_pilula(VERDE, " \ue77f $version ")}'

[battery]
format = '{_pilula(ROXO, " $symbol$percentage ", "#ffffff")}'
full_symbol = "󰁹 "
charging_symbol = "󰂄 "
discharging_symbol = "󰁾 "

[[battery.display]]
threshold = 100

[time]
disabled = false
time_format = "%H:%M"
format = '{_pilula(ROXO, " $time ", "#ffffff")}'
"""


def arquivo_starship() -> Path:
    return Path(os.environ.get("STARSHIP_CONFIG") or Path.home() / ".config" / "starship.toml")


def preset_ativo(arquivo: Path | None = None) -> bool:
    try:
        return "preset powerline" in (arquivo or arquivo_starship()).read_text(encoding="utf-8")[:120]
    except OSError:
        return False


def validar(texto: str) -> tuple[bool, str]:
    """Pede ao próprio Starship para montar um prompt com este arquivo."""
    with tempfile.TemporaryDirectory() as pasta:
        arq = Path(pasta) / "starship.toml"
        arq.write_text(texto, encoding="utf-8")
        env = {**os.environ, "STARSHIP_CONFIG": str(arq), "TERM": "xterm-256color"}
        try:
            r = executar(["starship", "prompt"], timeout=10, env=env, cwd=pasta)
        except ComandoAusente:
            return False, "o Starship não está instalado"
    return (True, "") if r.ok else (False, r.erro_legivel)


def aplicar_powerline(arquivo: Path | None = None) -> tuple[bool, str]:
    """Troca o prompt pelo preset. Devolve (ok, mensagem)."""
    ok, erro = validar(PRESET_POWERLINE)
    if not ok:
        return False, f"o Starship recusou o preset, nada foi alterado: {erro}"
    backup = arquivos.gravar(arquivo or arquivo_starship(), PRESET_POWERLINE)
    onde = f"backup em {backup}" if backup else "não havia prompt anterior"
    return True, f"Prompt powerline aplicado ({onde}). Vale para terminais novos."


def restaurar(arquivo: Path | None = None) -> tuple[bool, str]:
    backup = arquivos.restaurar_ultimo(arquivo or arquivo_starship())
    if backup is None:
        return False, "não há backup do starship.toml para restaurar"
    return True, f"Prompt restaurado de {backup.name}"
