"""AiLauncher: detecta IAs de linha de comando, prepara o workspace do tema
e abre o chat em um terminal novo. Tudo em listas de argumentos."""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from omarchy_manager.services import caminhos
from omarchy_manager.services.executor import abrir_desanexado
from omarchy_manager.services.log import logger

AGENTE_MD = Path(__file__).resolve().parents[3] / "agents" / "criador-de-temas.md"
ARQUIVO_AGENTE = "AGENTE-CRIADOR-DE-TEMAS.md"
_SLUG = re.compile(r"[^a-z0-9]+")


def slugificar(nome: str) -> str:
    slug = _SLUG.sub("-", nome.strip().lower()).strip("-")
    return slug or "novo-tema"


def localizar_agente() -> Path | None:
    candidatos = [
        AGENTE_MD,
        Path(__file__).resolve().parent.parent / "agents" / "criador-de-temas.md",
        Path("/usr/share/omarchy-manager/agents/criador-de-temas.md"),
        caminhos.DATA_DIR / "agents" / "criador-de-temas.md",
    ]
    return next((c for c in candidatos if c.is_file()), None)


@dataclass(frozen=True)
class AdaptadorIA:
    id: str
    nome: str
    executavel: str
    arquivo_instrucoes: str  # arquivo que a IA lê sozinha ao abrir no diretório

    def argumentos(self, caminho_exec: str, prompt: str) -> list[str]:
        """Flags conferidas no `--help` de cada CLI em 2026-11-13 (DECISOES.md, seção 7)."""
        if self.id == "claude":
            return [caminho_exec, "--append-system-prompt-file", ARQUIVO_AGENTE, prompt]
        if self.id == "codex":
            return [caminho_exec, prompt]
        if self.id == "opencode":
            return [caminho_exec, "--prompt", prompt]
        # copilot: `-p` é só não interativo; abre interativo e lê AGENTS.md sozinho.
        return [caminho_exec]


ADAPTADORES: tuple[AdaptadorIA, ...] = (
    AdaptadorIA("claude", "Claude Code", "claude", "CLAUDE.md"),
    AdaptadorIA("codex", "Codex", "codex", "AGENTS.md"),
    AdaptadorIA("opencode", "OpenCode", "opencode", "AGENTS.md"),
    AdaptadorIA("copilot", "GitHub Copilot CLI", "copilot", "AGENTS.md"),
)


@dataclass(frozen=True)
class AdaptadorTerminal:
    executavel: str

    def argumentos(self, caminho_exec: str, cwd: Path, comando: list[str]) -> list[str]:
        nome = Path(caminho_exec).name
        if nome == "xdg-terminal-exec":
            # É o que `omarchy-launch-terminal` usa: respeita o terminal padrão do usuário.
            return [caminho_exec, f"--dir={cwd}", *comando]
        if nome == "foot":
            return [caminho_exec, f"--working-directory={cwd}", "--", *comando]
        if nome == "alacritty":
            return [caminho_exec, "--working-directory", str(cwd), "-e", *comando]
        if nome == "kitty":
            return [caminho_exec, "--directory", str(cwd), *comando]
        if nome == "ghostty":
            return [caminho_exec, f"--working-directory={cwd}", "-e", *comando]
        if nome == "wezterm":
            return [caminho_exec, "start", "--cwd", str(cwd), "--", *comando]
        return [caminho_exec, "-e", *comando]


TERMINAIS = ("xdg-terminal-exec", "foot", "alacritty", "ghostty", "kitty", "wezterm")


@dataclass(frozen=True)
class IADisponivel:
    adaptador: AdaptadorIA
    caminho: str


class AiLauncher:
    def __init__(self, which=shutil.which, abrir=abrir_desanexado, workspaces: Path | None = None) -> None:
        self._which = which
        self._abrir = abrir
        self.workspaces = workspaces or caminhos.THEME_WORKSPACES_DIR

    def disponiveis(self) -> list[IADisponivel]:
        saida = []
        for a in ADAPTADORES:
            caminho = self._which(a.executavel)
            if caminho:
                saida.append(IADisponivel(a, caminho))
        return saida

    def terminal(self) -> tuple[AdaptadorTerminal, str] | None:
        preferido = os.environ.get("TERMINAL", "").strip()
        candidatos = ([preferido] if preferido else []) + list(TERMINAIS)
        for nome in candidatos:
            caminho = self._which(nome)
            if caminho:
                return AdaptadorTerminal(nome), caminho
        return None

    def preparar_workspace(self, nome_tema: str, adaptador: AdaptadorIA, tema_base: Path | None = None) -> Path:
        slug = slugificar(nome_tema)
        ws = caminhos.garantir_gravavel(self.workspaces / slug)
        ws.mkdir(parents=True, exist_ok=True)
        agente = localizar_agente()
        if agente is None:
            raise FileNotFoundError("agents/criador-de-temas.md não encontrado")
        texto = agente.read_text(encoding="utf-8")
        (ws / ARQUIVO_AGENTE).write_text(texto, encoding="utf-8")
        (ws / adaptador.arquivo_instrucoes).write_text(texto, encoding="utf-8")
        if tema_base is not None and tema_base.is_dir():
            destino = ws / "base" / tema_base.name
            if not destino.exists():
                shutil.copytree(tema_base, destino, symlinks=False, ignore=shutil.ignore_patterns(".git", "*.lock", "__pycache__"))
        logger.info("workspace de tema preparado: %s", ws)
        return ws

    def prompt_inicial(self, nome_tema: str, tema_base: Path | None) -> str:
        base = f"Há uma cópia do tema base em ./base/{tema_base.name}/ (só leitura de referência). " if tema_base else ""
        return (
            "Leia e siga AGENTE-CRIADOR-DE-TEMAS.md neste diretório antes de qualquer outra coisa. "
            f"Vamos criar o tema do Omarchy chamado '{nome_tema}'. {base}"
            "Comece pelas perguntas do item 2 do agente."
        )

    def abrir(self, ia: IADisponivel, nome_tema: str, tema_base: Path | None = None) -> list[str]:
        term = self.terminal()
        if term is None:
            raise FileNotFoundError("nenhum terminal encontrado (foot, alacritty, ghostty, kitty, wezterm)")
        adaptador_terminal, caminho_terminal = term
        ws = self.preparar_workspace(nome_tema, ia.adaptador, tema_base)
        comando = ia.adaptador.argumentos(ia.caminho, self.prompt_inicial(nome_tema, tema_base))
        argv = adaptador_terminal.argumentos(caminho_terminal, ws, comando)
        self._abrir(argv, cwd=str(ws))
        return argv
