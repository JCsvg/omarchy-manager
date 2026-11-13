import io
import json
import os
import tarfile

import pytest

from omarchy_manager.services import caminhos
from omarchy_manager.services.bundle import (
    ErroBundle,
    Manifesto,
    aviso_licenca,
    criar_bundle,
    extrair_para_temporario,
    instalar_recebido,
    listar_arquivos,
    sha256_arquivo,
    validar_bundle,
)


@pytest.fixture
def plugin(tmp_path, monkeypatch):
    monkeypatch.setattr(caminhos, "PROIBIDOS", (tmp_path / "proibido",))
    p = tmp_path / "meu.plugin"
    (p / "qml").mkdir(parents=True)
    (p / "manifest.json").write_text(json.dumps({"id": "meu.plugin", "name": "Meu", "license": "MIT"}))
    (p / "qml" / "Main.qml").write_text("Item {}")
    (p / "run.sh").write_text("#!/bin/sh\n")
    (p / "run.sh").chmod(0o755)
    (p / ".git").mkdir()
    (p / ".git" / "config").write_text("x")
    (p / "token.txt").write_text("segredo")
    (p / ".env").write_text("A=1")
    (p / "debug.log").write_text("log")
    os.symlink("/etc/passwd", p / "fora")
    os.symlink("manifest.json", p / "dentro")
    return p


def test_listar_exclui_o_que_deve(plugin):
    nomes = sorted(a.relative_to(plugin).as_posix() for a in listar_arquivos(plugin))
    assert nomes == ["dentro", "manifest.json", "qml/Main.qml", "run.sh"]


def test_criar_e_validar(plugin, tmp_path):
    arq, man, sha = criar_bundle("plugin", "meu.plugin", "Meu", plugin, tmp_path / "out", licenca="MIT", autor="JC")
    assert arq.name == "meu.plugin.omarchy-bundle" and sha == sha256_arquivo(arq)
    assert len(man.arquivos) == 4 and man.tamanho > 0
    lido = validar_bundle(arq, sha)
    assert lido.id == "meu.plugin" and lido.licenca == "MIT"
    with tarfile.open(arq) as tar:
        nomes = tar.getnames()
    assert "bundle.json" in nomes and "checksums.sha256" in nomes and "payload/.git/config" not in nomes
    assert "payload/token.txt" not in nomes


def test_hash_errado(plugin, tmp_path):
    arq, _, sha = criar_bundle("plugin", "meu.plugin", "Meu", plugin, tmp_path / "out")
    with pytest.raises(ErroBundle, match="SHA-256"):
        validar_bundle(arq, "0" * 64)


def test_conteudo_alterado(plugin, tmp_path):
    arq, _, _ = criar_bundle("plugin", "meu.plugin", "Meu", plugin, tmp_path / "out")
    # reempacota com um payload alterado, mantendo o bundle.json
    novo = tmp_path / "alterado.omarchy-bundle"
    with tarfile.open(arq) as orig, tarfile.open(novo, "w:gz") as dest:
        for m in orig.getmembers():
            dados = orig.extractfile(m).read() if m.isreg() else b""
            if m.name == "payload/run.sh":
                dados = b"#!/bin/sh\nrm -rf /\n"
                m.size = len(dados)
            dest.addfile(m, io.BytesIO(dados))
    with pytest.raises(ErroBundle, match="checksum|tamanho"):
        validar_bundle(novo)


def _bundle_bruto(tmp_path, membros):
    arq = tmp_path / "bruto.omarchy-bundle"
    man = Manifesto("plugin", "x.y", "X", arquivos=[]).to_json().encode()
    with tarfile.open(arq, "w:gz") as tar:
        for nome, dados, tipo in [("bundle.json", man, tarfile.REGTYPE), ("checksums.sha256", b"", tarfile.REGTYPE)] + membros:
            info = tarfile.TarInfo(nome)
            info.type = tipo
            info.size = len(dados)
            if tipo == tarfile.SYMTYPE:
                info.linkname = "/etc/passwd"
            tar.addfile(info, io.BytesIO(dados) if dados else None)
    return arq


@pytest.mark.parametrize(
    "membro, erro",
    [
        (("payload/../../x", b"a", tarfile.REGTYPE), "caminho rejeitado"),
        (("/etc/x", b"a", tarfile.REGTYPE), "caminho rejeitado"),
        (("payload/link", b"", tarfile.SYMTYPE), "não é arquivo regular"),
        (("outro/x", b"a", tarfile.REGTYPE), "caminho rejeitado"),
    ],
)
def test_rejeita_membros_perigosos(tmp_path, membro, erro):
    with pytest.raises(ErroBundle, match=erro):
        validar_bundle(_bundle_bruto(tmp_path, [membro]))


def test_lista_do_manifesto_tem_que_bater(tmp_path):
    with pytest.raises(ErroBundle, match="não bate"):
        validar_bundle(_bundle_bruto(tmp_path, [("payload/extra.txt", b"a", tarfile.REGTYPE)]))


def test_nao_e_tar(tmp_path):
    arq = tmp_path / "x.omarchy-bundle"
    arq.write_bytes(b"lixo")
    with pytest.raises(ErroBundle, match="tar.gz"):
        validar_bundle(arq)


def test_licenca():
    assert aviso_licenca("MIT") is None
    assert "ausente" in aviso_licenca("")
    assert "não reconhecida" in aviso_licenca("Proprietária")


def test_extrair_e_instalar_desligado(plugin, tmp_path):
    arq, _, sha = criar_bundle("plugin", "meu.plugin", "Meu", plugin, tmp_path / "out")
    pasta, man = extrair_para_temporario(arq, sha)
    assert (pasta / "manifest.json").is_file() and (pasta / "qml" / "Main.qml").is_file()
    assert os.access(pasta / "run.sh", os.X_OK)
    raiz = tmp_path / "plugins"
    with pytest.raises(ErroBundle):
        instalar_recebido(pasta, man, confirmado=False, raiz_plugins=raiz)
    r = instalar_recebido(pasta, man, confirmado=True, raiz_plugins=raiz)
    assert r.destino == raiz / "meu.plugin" and "DESLIGADO" in r.aviso
    # conflito: sem substituir falha; com substituir faz backup
    with pytest.raises(ErroBundle, match="já existe"):
        instalar_recebido(pasta, man, confirmado=True, raiz_plugins=raiz)
    r2 = instalar_recebido(pasta, man, confirmado=True, substituir=True, raiz_plugins=raiz, pasta_backups=tmp_path / "bk")
    assert r2.backup is not None and r2.backup.is_dir()


def test_limites(tmp_path, monkeypatch):
    monkeypatch.setattr(caminhos, "PROIBIDOS", (tmp_path / "proibido",))
    import omarchy_manager.services.bundle as b

    monkeypatch.setattr(b, "LIMITE_QUANTIDADE", 2)
    p = tmp_path / "p"
    p.mkdir()
    for i in range(3):
        (p / f"{i}.txt").write_text("xx")
    with pytest.raises(ErroBundle, match="arquivos"):
        criar_bundle("tema", "t", "T", p, tmp_path / "out")
    monkeypatch.setattr(b, "LIMITE_QUANTIDADE", 100)
    monkeypatch.setattr(b, "LIMITE_ARQUIVO", 1)
    with pytest.raises(ErroBundle, match="256 MiB"):
        criar_bundle("tema", "t", "T", p, tmp_path / "out")


def test_id_invalido(tmp_path, monkeypatch):
    monkeypatch.setattr(caminhos, "PROIBIDOS", (tmp_path / "proibido",))
    p = tmp_path / "p"
    p.mkdir()
    (p / "a").write_text("a")
    for ruim in ("../x", "a/b", ".oculto", ""):
        with pytest.raises(ErroBundle):
            criar_bundle("tema", ruim, "T", p, tmp_path / "out")
