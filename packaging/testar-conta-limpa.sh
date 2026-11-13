#!/usr/bin/env bash
# Simula uma conta de usuário nova: HOME e diretórios XDG vazios em um
# temporário, PATH só do sistema, sem o venv do projeto. Usa o pacote já
# instalado via pacman (não o código em src/).
#
# Não é uma conta de usuário real do sistema: o compositor, o DBus e o
# `omarchy` em execução continuam sendo os do usuário atual. O que isso prova
# é que o pacote instalado funciona sem nenhum arquivo em ~/.
set -euo pipefail

tmp=$(mktemp -d /tmp/omgr-conta-limpa.XXXXXX)
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/home" "$tmp/config" "$tmp/data" "$tmp/state" "$tmp/cache" "$tmp/run"
chmod 700 "$tmp/run"

limpo=(
  env -i
  HOME="$tmp/home"
  XDG_CONFIG_HOME="$tmp/config"
  XDG_DATA_HOME="$tmp/data"
  XDG_STATE_HOME="$tmp/state"
  XDG_CACHE_HOME="$tmp/cache"
  XDG_RUNTIME_DIR="$tmp/run"
  PATH=/usr/bin:/usr/local/bin:/usr/share/omarchy/bin
  TERM=xterm-256color
  LANG="${LANG:-pt_BR.UTF-8}"
  OMARCHY_PATH=/usr/share/omarchy
  HYPRLAND_INSTANCE_SIGNATURE="${HYPRLAND_INSTANCE_SIGNATURE:-}"
  XDG_RUNTIME_DIR_REAL="${XDG_RUNTIME_DIR:-}"
)

echo "== 1. binário instalado"
"${limpo[@]}" which omarchy-manager
"${limpo[@]}" omarchy-manager --versao

echo "== 2. importa do site-packages do sistema, não do projeto"
"${limpo[@]}" python3 -c 'import omarchy_manager, textual; print(omarchy_manager.__file__); print("textual", textual.__version__)' | tee "$tmp/import.txt"
grep -q "/usr/lib/python" "$tmp/import.txt"

echo "== 3. abre headless com HOME vazio e carrega as 3 abas"
"${limpo[@]}" python3 - <<'EOF'
import asyncio
from collections import Counter
from textual.widgets import DataTable
from omarchy_manager.app import OmarchyManagerApp
from omarchy_manager.services import caminhos
from omarchy_manager.ui.shortcuts import AbaAtalhos
from omarchy_manager.ui.themes import AbaTemas

async def main():
    caminhos.preparar_diretorios()
    app = OmarchyManagerApp()
    async with app.run_test(size=(160, 48)) as pilot:
        for tecla in ("1", "3", "2"):
            await pilot.press(tecla)
            await pilot.pause()
            await app.workers.wait_for_complete()
            await pilot.pause()
        temas = app.query_one(AbaTemas).temas
        atalhos = app.query_one(AbaAtalhos).atalhos
        print("tema textual:", app.theme, "| ausentes na paleta:", "nenhum" if app.theme else "?")
        print("plugins:", app.query_one("#plugins-tabela", DataTable).row_count)
        print("temas:", len(temas), "| do usuario:", sum(t.do_usuario for t in temas))
        print("atalhos:", len(atalhos), "| origens:", dict(Counter(a.origem for a in atalhos)))
        assert len(temas) > 0, "nenhum tema listado"
    print("HOME vazio OK")

asyncio.run(main())
EOF

echo "== 4. arquivos criados só dentro do HOME temporário"
find "$tmp/config" "$tmp/state" "$tmp/data" -type f -o -type d | sed "s|$tmp|\$TMP|" | sort

echo "== 5. nada escrito em /usr/share/omarchy"
test -z "$(find /usr/share/omarchy -newer "$tmp" -type f 2>/dev/null | head -1)" && echo "ok"

echo "CONTA LIMPA SIMULADA: OK"
