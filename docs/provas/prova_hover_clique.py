"""Prova técnica: hover e clique do mouse em uma tabela e um botão do Textual.

Roda headless com o Pilot. Verifica que:
1. mover o mouse sobre um botão dispara Enter/Leave (estado :hover);
2. clicar no botão dispara Button.Pressed;
3. clicar em uma linha da DataTable seleciona a linha;
4. um tooltip é exposto no hover.

Isso prova a lógica no Textual. A entrega dos eventos pelo terminal real
(Foot e Herdr) exige validação manual, ver DECISOES.md.
"""

import asyncio

from textual.app import App, ComposeResult
from textual.widgets import Button, DataTable


class Prova(App):
    pressionado = 0
    linha_selecionada = None

    def compose(self) -> ComposeResult:
        botao = Button("Ligar", id="ligar")
        botao.tooltip = "Liga o plugin"
        yield botao
        tabela = DataTable(id="tabela", cursor_type="row")
        yield tabela

    def on_mount(self) -> None:
        t = self.query_one(DataTable)
        t.add_columns("Estado", "Nome")
        t.add_row("ligado", "Clock", key="omarchy.clock")
        t.add_row("desligado", "Audio", key="omarchy.audio")

    def on_button_pressed(self, ev: Button.Pressed) -> None:
        self.pressionado += 1

    def on_data_table_row_highlighted(self, ev: DataTable.RowHighlighted) -> None:
        # Um clique move o cursor (RowHighlighted). RowSelected só vem com
        # Enter ou com um segundo clique na linha já destacada.
        self.linha_selecionada = ev.row_key.value


async def main() -> None:
    app = Prova()
    async with app.run_test(size=(60, 20)) as pilot:
        botao = app.query_one("#ligar", Button)
        await pilot.hover("#ligar")
        await pilot.pause()
        hover = botao.mouse_hover
        tooltip = botao.tooltip
        await pilot.click("#ligar")
        await pilot.pause()
        await pilot.click("#tabela", offset=(5, 2))
        await pilot.pause()
    print("hover:", hover, "| tooltip:", tooltip)
    print("cliques no botao:", app.pressionado)
    print("linha selecionada:", app.linha_selecionada)
    assert hover is True
    assert app.pressionado == 1
    assert app.linha_selecionada == "omarchy.audio"
    print("PROVA HOVER/CLIQUE: OK")


if __name__ == "__main__":
    asyncio.run(main())
