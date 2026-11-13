"""Captura de combinações globais (plano 6.3), solução 1: submap temporário.

Por `hyprctl eval`, define 1 vez por sessão do Hyprland um submap
`omarchy-manager-capture` com 1 bind por tecla conhecida. O handler Lua lê o
estado de Super, Ctrl, Alt e Shift, grava `MODS + TECLA` em um arquivo de
troca no XDG_RUNTIME_DIR e volta ao submap raiz. Esc grava `ESCAPE`.

A TUI entra no submap, espera o arquivo e sempre sai com `submap reset`.
Enquanto a prova manual com o JC não passar (ver DECISOES.md), o diálogo de
captura também aceita a tecla vinda do próprio terminal como fallback.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from omarchy_manager.services.hyprland import HyprlandService
from omarchy_manager.services.log import logger
from omarchy_manager.services.teclas import Combinacao, CombinacaoInvalida, normalizar

SUBMAP = "omarchy-manager-capture"
TIMEOUT_PADRAO = 15.0

TECLAS_CAPTURA: tuple[str, ...] = (
    *"ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    *(f"code:{n}" for n in range(10, 22)),  # 1..0, -, =
    *(f"F{n}" for n in range(1, 25)),
    "RETURN", "SPACE", "TAB", "BACKSPACE", "DELETE", "INSERT", "HOME", "END", "PRIOR", "NEXT",
    "UP", "DOWN", "LEFT", "RIGHT", "PRINT", "PAUSE", "MENU",
    "code:47", "code:48", "code:49", "code:51", "code:59", "code:60", "code:61", "code:94",  # ç ´ ' \ , . ; <
    "code:34", "code:35", "code:129",  # ´ [ e ponto do numérico (ABNT2)
    "XF86AudioRaiseVolume", "XF86AudioLowerVolume", "XF86AudioMute", "XF86AudioMicMute",
    "XF86AudioPlay", "XF86AudioPause", "XF86AudioNext", "XF86AudioPrev", "XF86AudioStop",
    "XF86MonBrightnessUp", "XF86MonBrightnessDown", "XF86Calculator", "XF86Search", "XF86HomePage",
    "XF86Mail", "XF86Explorer", "XF86Tools", "XF86Display", "XF86Sleep", "XF86PowerOff",
)

# Nomes de tecla do Textual -> nome do Hyprland.
TEXTUAL_PARA_HYPRLAND = {
    "enter": "RETURN", "escape": "ESCAPE", "space": "SPACE", "tab": "TAB", "backspace": "BACKSPACE",
    "delete": "DELETE", "insert": "INSERT", "home": "HOME", "end": "END", "pageup": "PRIOR", "pagedown": "NEXT",
    "up": "UP", "down": "DOWN", "left": "LEFT", "right": "RIGHT", "comma": "COMMA", "full_stop": "PERIOD",
    "less_than_sign": "LESS", "greater_than_sign": "GREATER", "slash": "SLASH", "minus": "MINUS",
    "equals_sign": "EQUAL", "semicolon": "SEMICOLON", "apostrophe": "APOSTROPHE", "grave_accent": "GRAVE",
    "left_square_bracket": "BRACKETLEFT", "right_square_bracket": "BRACKETRIGHT", "backslash": "BACKSLASH",
    "print_screen": "PRINT", "plus": "PLUS", "asterisk": "ASTERISK", "question_mark": "QUESTION",
    "colon": "COLON", "exclamation_mark": "EXCLAM", "at": "AT", "number_sign": "NUMBERSIGN",
    "dollar_sign": "DOLLAR", "percent_sign": "PERCENT", "ampersand": "AMPERSAND", "underscore": "UNDERSCORE",
    "quotation_mark": "QUOTEDBL", "circumflex_accent": "ASCIICIRCUM", "tilde": "ASCIITILDE",
    "vertical_line": "BAR", "left_curly_bracket": "BRACELEFT", "right_curly_bracket": "BRACERIGHT",
    "left_parenthesis": "PARENLEFT", "right_parenthesis": "PARENRIGHT",
}


def arquivo_troca_padrao() -> Path:
    base = Path(os.environ.get("XDG_RUNTIME_DIR") or f"/tmp/omarchy-manager-{os.getuid()}")
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    return base / "omarchy-manager-capture.txt"


def _lua_str(texto: str) -> str:
    return '"' + texto.replace("\\", "\\\\").replace('"', '\\"') + '"'


def gerar_lua_definicao(arquivo: Path, teclas: tuple[str, ...] = TECLAS_CAPTURA, submap: str = SUBMAP) -> str:
    """Lua enviado 1 vez por sessão. Idempotente via _G.omgr_capture_defined."""
    lista = ", ".join(_lua_str(t) for t in teclas)
    return f"""
if not _G.omgr_capture_defined then
  _G.omgr_capture_defined = true
  local arquivo = {_lua_str(str(arquivo))}
  local submap = {_lua_str(submap)}
  local modificadores = {{
    {{ "Super_L", "SUPER" }}, {{ "Super_R", "SUPER" }}, {{ "Control_L", "CTRL" }}, {{ "Control_R", "CTRL" }},
    {{ "Alt_L", "ALT" }}, {{ "Alt_R", "ALT" }}, {{ "Shift_L", "SHIFT" }}, {{ "Shift_R", "SHIFT" }},
  }}
  local function gravar(texto)
    local f = io.open(arquivo, "w")
    if f then f:write(texto, "\\n") f:close() end
    hl.dispatch(hl.dsp.submap("reset"))
  end
  local function handler(tecla)
    return function()
      local ativos = {{}}
      for _, m in ipairs(modificadores) do
        local ok, baixo = pcall(hl.is_key_down, m[1])
        if ok and baixo then ativos[m[2]] = true end
      end
      local partes = {{}}
      for _, n in ipairs({{ "SUPER", "CTRL", "ALT", "SHIFT" }}) do
        if ativos[n] then partes[#partes + 1] = n end
      end
      partes[#partes + 1] = tecla
      gravar(table.concat(partes, " + "))
    end
  end
  hl.define_submap(submap, function()
    hl.bind("ESCAPE", function() gravar("ESCAPE") end, {{ ignore_mods = true }})
    for _, tecla in ipairs({{ {lista} }}) do
      hl.bind(tecla, handler(tecla), {{ ignore_mods = true }})
    end
  end)
end
"""


def gerar_lua_entrar(submap: str = SUBMAP) -> str:
    return f"hl.dispatch(hl.dsp.submap({_lua_str(submap)}))"


def gerar_lua_sair() -> str:
    return 'hl.dispatch(hl.dsp.submap("reset"))'


def interpretar_resultado(texto: str) -> Combinacao | None:
    """`SUPER + SHIFT + Q` -> Combinacao; `ESCAPE` ou vazio -> None."""
    linha = texto.strip().splitlines()[0].strip() if texto.strip() else ""
    if not linha or linha.upper() == "ESCAPE":
        return None
    try:
        return normalizar(linha)
    except CombinacaoInvalida:
        return None


def combinacao_de_tecla_textual(key: str) -> Combinacao | None:
    """Converte o `event.key` do Textual ("ctrl+shift+q", "super+f5", "escape")."""
    if not key:
        return None
    partes = key.split("+")
    tecla = partes[-1]
    mods = [p for p in partes[:-1]]
    if tecla == "escape" and not mods:
        return None
    nome = TEXTUAL_PARA_HYPRLAND.get(tecla)
    if nome is None:
        if len(tecla) == 1:
            nome = tecla.upper()
        elif tecla.startswith("f") and tecla[1:].isdigit():
            nome = tecla.upper()
        else:
            return None
    if nome == "ESCAPE":
        return None
    texto = " + ".join(m.upper().replace("META", "ALT") for m in mods) + (" + " if mods else "") + nome
    try:
        return normalizar(texto)
    except CombinacaoInvalida:
        return None


class CapturaHyprland:
    def __init__(self, hyprland: HyprlandService | None = None, arquivo: Path | None = None) -> None:
        self.hyprland = hyprland or HyprlandService()
        self._arquivo = arquivo
        self._definido = False

    @property
    def arquivo(self) -> Path:
        if self._arquivo is None:
            self._arquivo = arquivo_troca_padrao()
        return self._arquivo

    def disponivel(self) -> bool:
        return bool(os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"))

    def preparar(self) -> bool:
        if self._definido:
            return True
        r = self.hyprland.eval_lua(gerar_lua_definicao(self.arquivo), timeout=10)
        if not r.ok or r.stderr.strip() or r.stdout.strip().startswith("error"):
            logger.warning("captura: definição do submap falhou: %s", r.erro_legivel)
            return False
        self._definido = True
        return True

    def iniciar(self) -> bool:
        if not self.disponivel() or not self.preparar():
            return False
        try:
            self.arquivo.unlink(missing_ok=True)
        except OSError:
            pass
        r = self.hyprland.eval_lua(gerar_lua_entrar(), timeout=5)
        if not r.ok:
            logger.warning("captura: entrar no submap falhou: %s", r.erro_legivel)
            return False
        logger.info("captura iniciada")
        return True

    def esperar(self, timeout: float = TIMEOUT_PADRAO, intervalo: float = 0.05) -> Combinacao | None:
        """Bloqueia até o arquivo aparecer ou o tempo acabar. Sempre reseta o submap."""
        fim = time.monotonic() + timeout
        try:
            while time.monotonic() < fim:
                if self.arquivo.is_file():
                    try:
                        texto = self.arquivo.read_text(encoding="utf-8")
                    except OSError:
                        texto = ""
                    if texto.strip():
                        return interpretar_resultado(texto)
                time.sleep(intervalo)
            return None
        finally:
            self.cancelar()

    def cancelar(self) -> None:
        try:
            self.hyprland.eval_lua(gerar_lua_sair(), timeout=5)
        except Exception as exc:  # nunca deixar o usuário preso no submap por erro nosso
            logger.error("captura: falha ao sair do submap: %s", exc)
        try:
            self.arquivo.unlink(missing_ok=True)
        except OSError:
            pass
