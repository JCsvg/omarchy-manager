"""Oferta e consulta pelo loopback (127.0.0.1): aprovação por conexão, lista limitada ao marcado, download conferido."""

import shutil

import pytest

from omarchy_manager.services import caminhos
from omarchy_manager.services.bundle import validar_bundle
from omarchy_manager.services.lan_share import ErroLan
from omarchy_manager.services.oferta import Catalogo, ClienteOferta, ServidorOferta

pytestmark = pytest.mark.skipif(shutil.which("openssl") is None, reason="openssl ausente")


@pytest.fixture
def cena(tmp_path, monkeypatch):
    monkeypatch.setattr(caminhos, "PROIBIDOS", (tmp_path / "proibido",))
    pasta = tmp_path / "projeto"
    pasta.mkdir()
    (pasta / "a.txt").write_text("a")
    (pasta / "meu-secret.txt").write_text("x")
    (tmp_path / "nota.txt").write_text("nota")
    (tmp_path / "nao-marcado.txt").write_text("nao")
    cat = Catalogo()
    cat.adicionar_pasta(pasta)
    cat.adicionar_arquivo(tmp_path / "nota.txt")
    chamadas = []
    resposta = {"ok": True}

    def aprovar(ip, codigo):
        chamadas.append((ip, codigo))
        return resposta["ok"]

    srv = ServidorOferta(cat, aprovar, "127.0.0.1", 0, espera_aprovacao=5)
    srv.iniciar()
    yield srv, cat, chamadas, resposta, tmp_path
    srv.encerrar()


def test_sem_aprovacao_nada_e_listado(cena):
    srv, cat, chamadas, resposta, tmp = cena
    c = ClienteOferta("127.0.0.1", srv.porta)
    c.sondar()
    assert chamadas == []  # só conectar e ler o certificado não pede nada nem expõe nada
    with pytest.raises(ErroLan, match="403"):
        c.listar()
    c._sessao = "inventado"
    with pytest.raises(ErroLan, match="403"):
        c.baixar("1", tmp / "d")
    resposta["ok"] = False
    with pytest.raises(ErroLan, match="recusou"):
        c.autorizar()
    assert chamadas[0][0] == "127.0.0.1" and chamadas[0][1] == srv.codigo


def test_aprovado_lista_so_o_marcado_e_baixa(cena):
    srv, cat, chamadas, resposta, tmp = cena
    c = ClienteOferta("127.0.0.1", srv.porta)
    assert c.sondar() == srv.codigo and len(srv.codigo.split()) == 6
    c.autorizar()
    itens = c.listar()
    assert [(i["tipo"], i["nome"]) for i in itens] == [("pasta", "projeto"), ("arquivo", "nota.txt")]
    assert all("caminho" not in i for i in itens)
    arq, meta = c.baixar(itens[0]["id"], tmp / "d")
    assert meta["tipo"] == "pasta"
    man = validar_bundle(arq, meta["sha256"])
    assert {a.caminho for a in man.arquivos} == {"a.txt"}  # meu-secret.txt ficou de fora
    arq2, meta2 = c.baixar(itens[1]["id"], tmp / "d")
    assert meta2["nome"] == "nota.txt" and arq2.read_text() == "nota"
    with pytest.raises(ErroLan, match="404"):
        c.baixar("99", tmp / "d")
    # o que não foi marcado não existe para o outro lado; desmarcar tira da lista na hora
    cat.remover(itens[1]["id"])
    assert [i["nome"] for i in c.listar()] == ["projeto"]


def test_token_de_outro_ip_nao_vale(cena):
    srv, *_ = cena
    c = ClienteOferta("127.0.0.1", srv.porta)
    c.sondar()
    c.autorizar()
    assert srv.sessao_valida(c._sessao, "127.0.0.1")
    assert not srv.sessao_valida(c._sessao, "10.0.0.9")


def test_fingerprint_trocada_recusa(cena):
    srv, *_ = cena
    c = ClienteOferta("127.0.0.1", srv.porta)
    c.sondar()
    c.fingerprint = "00" * 32
    with pytest.raises(ErroLan, match="certificado mudou"):
        c.autorizar()


def test_encerrada_recusa(cena):
    srv, *_ = cena
    c = ClienteOferta("127.0.0.1", srv.porta)
    c.sondar()
    c.autorizar()
    srv._encerrado = True
    with pytest.raises(ErroLan, match="410"):
        c.listar()


def test_porta_ocupada_levanta_erro(cena):
    srv, cat, *_ = cena
    outro = ServidorOferta(cat, lambda *a: True, "127.0.0.1", srv.porta)
    with pytest.raises(ErroLan, match="escutar"):
        outro.iniciar()
