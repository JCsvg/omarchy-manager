"""Nomes e descrições de plugins em pt-BR.

Os manifestos dos plugins vêm em inglês e não trazem tradução. Aqui há um
arquivo embutido (`data/plugins-pt-BR.json`, id -> nome e descrição) e um
arquivo do usuário, com o mesmo formato, que tem prioridade:
`~/.config/omarchy-manager/plugins-pt-BR.json`. Sem tradução, vale o texto
original do manifesto.
"""

from __future__ import annotations

import json
from pathlib import Path

from omarchy_manager.services import caminhos

EMBUTIDO = Path(__file__).resolve().parent.parent / "data" / "plugins-pt-BR.json"


def _ler(arquivo: Path) -> dict[str, dict[str, str]]:
    try:
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(dados, dict):
        return {}
    saida = {}
    for pid, item in dados.items():
        if isinstance(item, dict):
            saida[str(pid)] = {k: str(v) for k, v in item.items() if k in ("nome", "descricao") and isinstance(v, str) and v.strip()}
    return saida


def carregar(arquivo_usuario: Path | None = None, embutido: Path | None = None) -> dict[str, dict[str, str]]:
    tabela = _ler(embutido or EMBUTIDO)
    for pid, item in _ler(arquivo_usuario or (caminhos.CONFIG_DIR / "plugins-pt-BR.json")).items():
        tabela[pid] = {**tabela.get(pid, {}), **item}
    return tabela


def traduzir(tabela: dict[str, dict[str, str]], plugin_id: str, nome: str, descricao: str) -> tuple[str, str]:
    item = tabela.get(plugin_id, {})
    return item.get("nome", nome), item.get("descricao", descricao)
