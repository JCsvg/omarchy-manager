"""Normalização de combinações de teclas e detecção de conflito.

Convenções:
- modmask segue o Hyprland: SHIFT=1, CAPS=2, CTRL=4, ALT=8, MOD2=16,
  MOD3=32, SUPER=64, MOD5=128;
- a forma canônica ordena SUPER, CTRL, ALT, SHIFT e escreve a tecla em
  maiúsculas, exceto `code:NN`, que fica como está;
- duas combinações conflitam quando têm o mesmo modmask e a mesma tecla, por
  nome ou por keycode resolvido.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MODIFICADORES = {
    "SHIFT": 1,
    "CAPS": 2,
    "CTRL": 4,
    "CONTROL": 4,
    "ALT": 8,
    "MOD2": 16,
    "MOD3": 32,
    "SUPER": 64,
    "WIN": 64,
    "LOGO": 64,
    "META": 64,
    "MOD4": 64,
    "MOD5": 128,
}
ORDEM_CANONICA = (("SUPER", 64), ("CTRL", 4), ("ALT", 8), ("SHIFT", 1))

# keycodes XKB (evdev + 8) que o Omarchy e o teclado ABNT2 usam em `code:NN`.
KEYCODE_PARA_NOME = {
    10: "1", 11: "2", 12: "3", 13: "4", 14: "5", 15: "6", 16: "7", 17: "8", 18: "9", 19: "0",
    20: "MINUS", 21: "EQUAL", 47: "CCEDILLA", 59: "COMMA", 60: "PERIOD", 61: "SLASH",
    94: "LESS", 129: "KP_DECIMAL",
}
NOME_PARA_KEYCODE = {v: k for k, v in KEYCODE_PARA_NOME.items()}

ALIASES_TECLA = {
    "ENTER": "RETURN", "ESC": "ESCAPE", "SPC": "SPACE", "PGUP": "PRIOR", "PGDN": "NEXT",
    "PAGE_UP": "PRIOR", "PAGE_DOWN": "NEXT", "COMMA": "COMMA", ",": "COMMA", ".": "PERIOD",
    "/": "SLASH", "-": "MINUS", "=": "EQUAL", "<": "LESS", "Ç": "CCEDILLA", "~": "GRAVE",
    "'": "APOSTROPHE", ";": "SEMICOLON", "[": "BRACKETLEFT", "]": "BRACKETRIGHT", "\\": "BACKSLASH",
}

_SEPARADORES = re.compile(r"[+\s,]+")


class CombinacaoInvalida(ValueError):
    pass


@dataclass(frozen=True)
class Combinacao:
    modmask: int
    key: str
    keycode: int = 0

    @property
    def canonica(self) -> str:
        return combinacao_legivel(self.modmask, self.key, self.keycode)

    @property
    def chave_conflito(self) -> tuple[int, str]:
        """Identidade usada para comparar duas combinações."""
        nome = self.key.upper()
        if nome.startswith("CODE:"):
            codigo = int(nome[5:])
            nome = KEYCODE_PARA_NOME.get(codigo, nome)
        elif self.keycode:
            nome = KEYCODE_PARA_NOME.get(self.keycode, nome)
        return (self.modmask, nome)


def modificadores_legiveis(modmask: int) -> list[str]:
    nomes = [nome for nome, bit in ORDEM_CANONICA if modmask & bit]
    restantes = modmask & ~sum(bit for _, bit in ORDEM_CANONICA)
    for nome, bit in (("CAPS", 2), ("MOD2", 16), ("MOD3", 32), ("MOD5", 128)):
        if restantes & bit:
            nomes.append(nome)
    return nomes


def combinacao_legivel(modmask: int, key: str, keycode: int = 0) -> str:
    tecla = key.strip()
    if not tecla and keycode:
        tecla = f"code:{keycode}"
    if tecla.lower().startswith("code:"):
        tecla = "code:" + tecla[5:]
    else:
        tecla = tecla.upper()
    partes = modificadores_legiveis(modmask) + ([tecla] if tecla else [])
    return " + ".join(partes)


def normalizar(texto: str) -> Combinacao:
    """Aceita "Super+Shift+q", "SUPER SHIFT, Q", "super + code:59" etc."""
    partes = [p for p in _SEPARADORES.split(texto.strip()) if p]
    if not partes:
        raise CombinacaoInvalida("combinação vazia")
    modmask = 0
    teclas: list[str] = []
    for parte in partes:
        maiusc = parte.upper()
        if maiusc in MODIFICADORES:
            modmask |= MODIFICADORES[maiusc]
        else:
            teclas.append(parte)
    if len(teclas) != 1:
        raise CombinacaoInvalida(f"esperada exatamente 1 tecla, veio {len(teclas)}: {texto!r}")
    tecla = teclas[0]
    if tecla.lower().startswith("code:"):
        try:
            codigo = int(tecla[5:])
        except ValueError as exc:
            raise CombinacaoInvalida(f"keycode inválido: {tecla!r}") from exc
        return Combinacao(modmask, f"code:{codigo}", codigo)
    nome = ALIASES_TECLA.get(tecla.upper(), ALIASES_TECLA.get(tecla, tecla.upper()))
    return Combinacao(modmask, nome, NOME_PARA_KEYCODE.get(nome, 0))


def conflitam(a: Combinacao, b: Combinacao) -> bool:
    return a.chave_conflito == b.chave_conflito


def texto_hyprland(c: Combinacao) -> str:
    """Forma aceita por `o.bind`/`hl.bind`: "SUPER + SHIFT + Q"."""
    return c.canonica
