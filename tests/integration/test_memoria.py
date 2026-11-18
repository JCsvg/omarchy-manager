"""Guarda de memória: o RSS depois de uso intenso não pode passar de um teto."""

import gc
import os

from test_app_webapps import _montar

TETO_MB = 220  # medido ~133 MB pós-uso (antes da correção: 298 MB)
TETO_CRESCIMENTO_MB = 90  # medido ~49 MB, caches do Textual que estabilizam (antes: 200 MB)


def rss_mb() -> float:
    with open(f"/proc/{os.getpid()}/status") as f:
        for linha in f:
            if linha.startswith("VmRSS:"):
                return int(linha.split()[1]) / 1024
    return 0.0


async def _uso(app, pilot, voltas):
    for _ in range(voltas):
        for aba in app.abas_visiveis():
            app.action_aba(aba)
            await pilot.pause(0.01)
            app.action_ajuda_aba()
            await pilot.pause(0.01)
            if len(app.screen_stack) > 1:
                app.screen.dismiss(None)
                await pilot.pause(0.01)
    gc.collect()


async def test_rss_nao_cresce_com_o_uso(tmp_path, executor, monkeypatch):
    app = _montar(tmp_path, executor, monkeypatch, aba_inicial="plugins")
    async with app.run_test(size=(170, 45)) as pilot:
        await pilot.pause(0.3)
        await _uso(app, pilot, 3)
        base = rss_mb()
        await _uso(app, pilot, 30)
        fim = rss_mb()
        print(f"RSS aquecido {base:.1f} MB, pos-uso {fim:.1f} MB")
        assert fim < TETO_MB
        assert fim - base < TETO_CRESCIMENTO_MB
