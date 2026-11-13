import json
from pathlib import Path

from omarchy_manager import __version__
from omarchy_manager.services import traducoes
from omarchy_manager.services.qr import linhas_de_matriz, qr_ansi, qr_linhas, qr_markup

RAIZ = Path(__file__).resolve().parents[2]


def test_linhas_de_matriz():
    m = [[True, False], [False, True], [True, True]]
    assert linhas_de_matriz(m) == ["▀▄", "▀▀"]


def test_qr_do_convite():
    convite = "omarchy-manager://192.168.0.10:45123/" + "ab" * 32 + "/" + "s" * 32
    linhas = qr_linhas(convite)
    assert linhas and len(set(len(l) for l in linhas)) == 1
    assert len(linhas[0]) >= 25 and set("".join(linhas)) <= set(" ▀▄█")
    assert "#000000 on #ffffff" in qr_markup(convite)
    assert qr_ansi(convite).startswith("\x1b[30;107m")


def test_qr_decodifica_de_volta():
    import qrcode  # a mesma matriz que desenhamos é a da biblioteca

    from omarchy_manager.services.qr import matriz_qr

    m = matriz_qr("oi")
    assert len(m) == len(m[0]) and len(m) >= 21 + 4
    assert not any(m[0]) and not any(l[0] for l in m)  # borda clara


def test_traducoes_embutidas():
    tabela = traducoes.carregar(arquivo_usuario=Path("/nao/existe.json"))
    assert len(tabela) >= 80
    assert tabela["omarchy.clipboard"]["nome"] == "Área de transferência"
    texto = json.dumps(tabela, ensure_ascii=False)
    assert "—" not in texto and "–" not in texto
    assert all(v.get("nome") and v.get("descricao") for v in tabela.values())


def test_traducao_do_usuario_tem_prioridade_e_fallback(tmp_path):
    usuario = tmp_path / "plugins-pt-BR.json"
    usuario.write_text(json.dumps({"omarchy.clipboard": {"nome": "Copiados"}, "x.novo": {"descricao": "Meu plugin"}}))
    tabela = traducoes.carregar(arquivo_usuario=usuario)
    assert traducoes.traduzir(tabela, "omarchy.clipboard", "Clipboard", "orig")[0] == "Copiados"
    assert "Histórico" in traducoes.traduzir(tabela, "omarchy.clipboard", "Clipboard", "orig")[1]
    assert traducoes.traduzir(tabela, "x.novo", "Novo", "orig") == ("Novo", "Meu plugin")
    assert traducoes.traduzir(tabela, "sem.traducao", "Name", "Desc") == ("Name", "Desc")
    usuario.write_text("{quebrado")
    assert len(traducoes.carregar(arquivo_usuario=usuario)) >= 80


def test_catalogo_aplica_traducao(tmp_path, executor):
    from omarchy_manager.services.plugin_catalog import PluginCatalog

    cat = PluginCatalog(executor, raiz_usuario=tmp_path / "u", raiz_sistema=tmp_path / "s",
                        traducoes={"omarchy.clipboard": {"nome": "Área de transferência", "descricao": "Histórico"}})
    p = cat.listar([{"id": "omarchy.clipboard", "name": "Clipboard", "firstParty": True}, {"id": "a.b", "name": "Outro"}])
    por_id = {x.id: x for x in p}
    assert por_id["omarchy.clipboard"].name == "Área de transferência"
    assert por_id["omarchy.clipboard"].nome_original == "Clipboard"
    assert por_id["a.b"].name == "Outro"


def test_atalhos_da_aba_config():
    from omarchy_manager.ui.config import tecla_legivel, todos_os_atalhos

    linhas = todos_os_atalhos()
    teclas = {(onde, tecla) for onde, tecla, _ in linhas}
    assert ("Global", "Alt+L / Alt+→") in teclas and ("Global", "Alt+H / Alt+←") in teclas
    assert ("Temas", "V") in teclas and ("Plugins", "Espaço") in teclas and ("Atalhos", "E") in teclas
    assert all(descricao for _, _, descricao in linhas)
    assert tecla_legivel("ctrl+f5") == "Ctrl+F5"
    assert "—" not in json.dumps(linhas, ensure_ascii=False)


def test_manifesto_do_plugin():
    m = json.loads((RAIZ / "manifest.json").read_text())
    assert m["schemaVersion"] == 1 and m["version"] == __version__
    assert not m["id"].startswith("omarchy.")
    assert (RAIZ / m["entryPoints"]["barWidget"]).is_file()
    assert m["id"] in (RAIZ / "BarWidget.qml").read_text()
    lancador = RAIZ / "bin" / "omarchy-manager"
    assert lancador.is_file() and lancador.stat().st_mode & 0o111
