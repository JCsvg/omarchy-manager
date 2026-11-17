"""Serviços da aba Compartilhar: IPs, teste de porta, catálogo e recebidos. Rede só em 127.0.0.1."""

import json
import socket

import pytest

from omarchy_manager.services import caminhos, recebidos
from omarchy_manager.services.bundle import ErroBundle, criar_bundle
from omarchy_manager.services.oferta import Catalogo
from omarchy_manager.services.rede import interpretar_ip_addr
from omarchy_manager.services.rede import testar_porta as _testar

IP_ADDR = json.dumps([
    {"ifname": "lo", "flags": ["LOOPBACK", "UP"], "addr_info": [{"family": "inet", "local": "127.0.0.1"}]},
    {"ifname": "wlan0", "flags": ["UP"], "addr_info": [{"family": "inet", "local": "192.168.0.10"}]},
    {"ifname": "enp3s0", "flags": ["UP"], "addr_info": [{"family": "inet", "local": "10.0.0.5"}, {"family": "inet6", "local": "fe80::1"}]},
    {"ifname": "tun0", "flags": ["UP"], "addr_info": []},
])


def test_ips_sem_loopback_com_interface():
    r = interpretar_ip_addr(IP_ADDR)
    assert [(i.interface, i.ip, i.tipo) for i in r] == [("wlan0", "192.168.0.10", "Wi-Fi"), ("enp3s0", "10.0.0.5", "cabo")]
    assert interpretar_ip_addr("lixo") == []


def test_porta_livre_e_ocupada():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen(1)
    ocupada = s.getsockname()[1]
    try:
        ok, motivo = _testar("127.0.0.1", ocupada)
        assert not ok and "ocupada" in motivo
    finally:
        s.close()
    livre = socket.socket()
    livre.bind(("127.0.0.1", 0))
    n = livre.getsockname()[1]
    livre.close()
    assert _testar("127.0.0.1", n) == (True, "livre")


@pytest.mark.parametrize("entrada", ["", "abc", "0", "65536", "-1"])
def test_porta_invalida(entrada):
    assert _testar("127.0.0.1", entrada)[0] is False


def test_porta_ip_alheio():
    ok, motivo = _testar("203.0.113.9", 50000)
    assert not ok and "IP" in motivo


@pytest.fixture
def pasta(tmp_path, monkeypatch):
    monkeypatch.setattr(caminhos, "PROIBIDOS", (tmp_path / "proibido",))
    p = tmp_path / "projeto"
    (p / "sub").mkdir(parents=True)
    (p / "a.txt").write_text("a")
    (p / "sub" / "b.txt").write_text("b")
    (p / "meu-token.txt").write_text("segredo")
    (p / ".env").write_text("X=1")
    (p / "credential.json").write_text("{}")
    return p


def test_catalogo_vazio_por_padrao_e_lista_sem_caminho(pasta):
    c = Catalogo()
    assert c.listagem_publica() == []
    c.adicionar_pasta(pasta)
    (lista,) = c.listagem_publica()
    assert lista["tipo"] == "pasta" and lista["arquivos"] == 2  # a.txt e sub/b.txt
    assert str(pasta) not in json.dumps(lista)


def test_pasta_vira_bundle_sem_arquivos_sensiveis(pasta, tmp_path):
    c = Catalogo()
    item = c.adicionar_pasta(pasta)
    arq, sha, nome = c.preparar(item, tmp_path / "out")
    _, man, _ = criar_bundle("pasta", "x", "x", pasta, tmp_path / "out2")
    nomes = {a.caminho for a in man.arquivos}
    assert nomes == {"a.txt", "sub/b.txt"}
    assert nome.endswith(".omarchy-bundle") and len(sha) == 64


def test_arquivo_sensivel_recusado_e_comum_aceito(pasta):
    c = Catalogo()
    for ruim in ("meu-token.txt", ".env", "credential.json"):
        with pytest.raises(ErroBundle):
            c.adicionar_arquivo(pasta / ruim)
    item = c.adicionar_arquivo(pasta / "a.txt")
    assert c.adicionar_arquivo(pasta / "a.txt") is item  # sem duplicar
    c.remover(item.id)
    assert c.itens() == []
    with pytest.raises(ErroBundle):
        c.adicionar_pasta(pasta / "nao-existe")


def test_recebidos_nao_sobrescreve_sem_perguntar(tmp_path, monkeypatch):
    monkeypatch.setattr(caminhos, "PROIBIDOS", (tmp_path / "proibido",))
    monkeypatch.setattr(caminhos, "BACKUPS_DIR", tmp_path / "bk")
    base = tmp_path / "dl"
    a = tmp_path / "x1"
    a.write_text("novo")
    destino = recebidos.guardar_arquivo(a, "../../fugiu.txt", base)
    assert destino == base.resolve() / "fugiu.txt" and destino.read_text() == "novo"
    b = tmp_path / "x2"
    b.write_text("outro")
    with pytest.raises(recebidos.JaExiste):
        recebidos.guardar_arquivo(b, "fugiu.txt", base)
    assert destino.read_text() == "novo"
    recebidos.guardar_arquivo(b, "fugiu.txt", base, sobrescrever=True)
    assert destino.read_text() == "outro" and len(list((tmp_path / "bk").iterdir())) == 1


def test_guardar_pasta(pasta, tmp_path, monkeypatch):
    monkeypatch.setattr(caminhos, "BACKUPS_DIR", tmp_path / "bk")
    arq, _, sha = criar_bundle("pasta", "projeto", "projeto", pasta, tmp_path / "out")
    base = tmp_path / "dl"
    d = recebidos.guardar_pasta(arq, sha, "projeto", base)
    assert (d / "sub" / "b.txt").read_text() == "b" and not (d / ".env").exists()
    with pytest.raises(recebidos.JaExiste):
        recebidos.guardar_pasta(arq, sha, "projeto", base)
