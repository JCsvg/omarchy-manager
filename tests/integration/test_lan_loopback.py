"""Transferência HTTPS real pelo loopback: os 2 lados na mesma máquina.

Isto prova certificado temporário, fingerprint fixada, segredo, 1 download,
expiração e validação do pacote recebido. NÃO prova descoberta mDNS entre
dispositivos distintos nem redes com isolamento de clientes (DECISOES.md).
"""

import shutil
import time

import pytest

from omarchy_manager.services import caminhos
from omarchy_manager.services.bundle import criar_bundle, extrair_para_temporario, validar_bundle
from omarchy_manager.services.lan_share import (
    ErroLan,
    ServidorEnvio,
    baixar,
    codigo_de_confirmacao,
    interpretar_convite,
)

pytestmark = pytest.mark.skipif(shutil.which("openssl") is None, reason="openssl ausente")


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    monkeypatch.setattr(caminhos, "PROIBIDOS", (tmp_path / "proibido",))
    t = tmp_path / "meu-tema"
    (t / "backgrounds").mkdir(parents=True)
    (t / "colors.toml").write_text('mode = "dark"\nbackground = "#000000"\n')
    (t / "backgrounds" / "a.png").write_bytes(b"\x89PNG" + b"\x00" * 2000)
    return criar_bundle("tema", "meu-tema", "Meu Tema", t, tmp_path / "out", licenca="CC-BY-4.0")


def test_codigo_igual_nos_dois_lados():
    fp = "ab" * 32
    assert codigo_de_confirmacao(fp, "s1") == codigo_de_confirmacao(fp, "s1")
    assert codigo_de_confirmacao(fp, "s1") != codigo_de_confirmacao(fp, "s2")
    assert len(codigo_de_confirmacao(fp, "s1").split()) == 6


def test_transferencia_loopback(bundle, tmp_path):
    arq, man, sha = bundle
    srv = ServidorEnvio(arq, sha, host_anuncio="127.0.0.1", bind="127.0.0.1", publicar_mdns=False)
    s = srv.iniciar()
    try:
        assert s.ativa and len(s.fingerprint) == 64
        host, porta, fp, segredo = interpretar_convite(s.convite)
        assert (host, porta, fp, segredo) == ("127.0.0.1", s.porta, s.fingerprint, s.segredo)
        # o receptor calcula o mesmo código que o emissor mostra
        assert codigo_de_confirmacao(fp, segredo) == s.codigo

        # fingerprint errada: recusa antes de mandar o segredo
        with pytest.raises(ErroLan, match="fingerprint"):
            baixar(host, porta, "00" * 32, segredo, tmp_path / "nao.bundle")
        assert not s.baixado

        # segredo errado: 403, continua ativa
        with pytest.raises(ErroLan, match="403"):
            baixar(host, porta, fp, "errado", tmp_path / "nao.bundle")
        assert s.ativa

        destino, sha_informado = baixar(host, porta, fp, segredo, tmp_path / "recebido.omarchy-bundle")
        assert sha_informado == sha
        assert validar_bundle(destino, sha).id == "meu-tema"
        pasta, _ = extrair_para_temporario(destino, sha)
        assert (pasta / "colors.toml").is_file()

        # 1 download: a 2ª tentativa recebe 410
        assert s.baixado and not s.ativa
        with pytest.raises(ErroLan, match="410"):
            baixar(host, porta, fp, segredo, tmp_path / "de-novo.bundle")
        assert srv.esperar() is True
    finally:
        srv.encerrar()
    assert s.segredo == "" and not srv._tmp.exists()


def test_expiracao(bundle, tmp_path):
    arq, _, sha = bundle
    srv = ServidorEnvio(arq, sha, host_anuncio="127.0.0.1", bind="127.0.0.1", publicar_mdns=False)
    s = srv.iniciar()
    try:
        s.expira_em = time.monotonic() - 1
        assert not s.ativa
        with pytest.raises(ErroLan, match="410"):
            baixar("127.0.0.1", s.porta, s.fingerprint, s.segredo, tmp_path / "x.bundle")
        assert srv.esperar() is False
    finally:
        srv.encerrar()


def test_convite_invalido():
    with pytest.raises(ErroLan):
        interpretar_convite("https://exemplo.com/x")
