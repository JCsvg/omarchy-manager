import pytest

from omarchy_manager.services import caminhos
from omarchy_manager.services.omarchy import OmarchyService
from omarchy_manager.services.temas import ThemeService, nome_de_slug


def _ambiente(tmp_path, executor, fixtures, monkeypatch):
    sistema, usuario, fundos = tmp_path / "sistema", tmp_path / "usuario", tmp_path / "fundos"
    for raiz, slug, cores in (
        (sistema, "tokyo-night", "colors_dark.toml"),
        (sistema, "catppuccin-latte", "colors_light.toml"),
        (usuario, "signature", "colors_dark.toml"),
        (usuario, "quebrado", None),
    ):
        (raiz / slug / "backgrounds").mkdir(parents=True)
        if cores:
            (raiz / slug / "colors.toml").write_text((fixtures / cores).read_text())
        (raiz / slug / "backgrounds" / "a.png").write_bytes(b"png")
        (raiz / slug / "backgrounds" / "notas.txt").write_text("nao e imagem")
    (fundos / "signature").mkdir(parents=True)
    (fundos / "signature" / "meu.jpg").write_bytes(b"jpg")
    estado = tmp_path / "estado"
    estado.mkdir()
    (estado / "theme.name").write_text("signature\n")
    monkeypatch.setattr(caminhos, "OMARCHY_STATE_CURRENT", estado)
    executor.responder(["omarchy", "theme", "list"], "Catppuccin Latte\nQuebrado\nSignature\nTokyo Night\nSem Pasta\n")
    svc = ThemeService(
        OmarchyService(executor),
        raiz_usuario=usuario,
        raiz_sistema=sistema,
        raiz_fundos_usuario=fundos,
        arquivo_config=tmp_path / "cfg" / "config.toml",
    )
    return svc, sistema, usuario, fundos


def test_nome_de_slug():
    assert nome_de_slug("tokyo-night") == "Tokyo Night"
    assert nome_de_slug("catppuccin-latte") == "Catppuccin Latte"


def test_listar(tmp_path, executor, fixtures, monkeypatch):
    svc, sistema, usuario, fundos = _ambiente(tmp_path, executor, fixtures, monkeypatch)
    temas = {t.slug: t for t in svc.listar()}
    assert set(temas) == {"tokyo-night", "catppuccin-latte", "signature", "quebrado"}
    assert temas["signature"].atual and temas["signature"].do_usuario
    assert not temas["tokyo-night"].do_usuario
    assert temas["catppuccin-latte"].paleta is not None and not temas["catppuccin-latte"].paleta.escuro
    assert temas["quebrado"].paleta is None
    assert [f.name for f in temas["signature"].fundos] == ["a.png", "meu.jpg"]
    assert temas["tokyo-night"].fundo_padrao is None


def test_fundo_padrao_grava_e_le(tmp_path, executor, fixtures, monkeypatch):
    svc, sistema, usuario, fundos = _ambiente(tmp_path, executor, fixtures, monkeypatch)
    sig = next(t for t in svc.listar() if t.slug == "signature")
    gravado = svc.definir_fundo_padrao(sig, fundos / "signature" / "meu.jpg")
    assert gravado == (fundos / "signature" / "meu.jpg").resolve()
    texto = svc.arquivo_config.read_text()
    assert "[theme_defaults]" in texto and "signature" in texto
    assert svc.fundos_padrao() == {"signature": str(gravado)}
    assert next(t for t in svc.listar() if t.slug == "signature").fundo_padrao == gravado

    svc.definir_fundo_padrao(sig, None)
    assert svc.fundos_padrao() == {}


def test_fundo_fora_das_pastas_e_recusado(tmp_path, executor, fixtures, monkeypatch):
    svc, sistema, usuario, fundos = _ambiente(tmp_path, executor, fixtures, monkeypatch)
    sig = next(t for t in svc.listar() if t.slug == "signature")
    fora = tmp_path / "fora.png"
    fora.write_bytes(b"x")
    with pytest.raises(ValueError):
        svc.definir_fundo_padrao(sig, fora)
    # de outro tema também não
    with pytest.raises(ValueError):
        svc.definir_fundo_padrao(sig, sistema / "tokyo-night" / "backgrounds" / "a.png")
    # arquivo que não é imagem
    with pytest.raises(ValueError):
        svc.definir_fundo_padrao(sig, usuario / "signature" / "backgrounds" / "notas.txt")


def test_aplicar_tema_e_fundo(tmp_path, executor, fixtures, monkeypatch):
    svc, sistema, usuario, fundos = _ambiente(tmp_path, executor, fixtures, monkeypatch)
    sig = next(t for t in svc.listar() if t.slug == "signature")
    imagem = svc.definir_fundo_padrao(sig, usuario / "signature" / "backgrounds" / "a.png")
    sig = next(t for t in svc.listar() if t.slug == "signature")
    executor.responder(["omarchy", "theme", "set", "signature"], "")
    executor.responder(["omarchy", "theme", "bg", "set", str(imagem)], "")
    r = svc.aplicar(sig)
    assert r.tema_ok and r.fundo_ok and not r.pedir_nova_imagem
    assert ("omarchy", "theme", "set", "signature") in executor.chamadas
    assert ("omarchy", "theme", "bg", "set", str(imagem)) in executor.chamadas


def test_aplicar_com_imagem_sumida_pede_nova(tmp_path, executor, fixtures, monkeypatch):
    svc, sistema, usuario, fundos = _ambiente(tmp_path, executor, fixtures, monkeypatch)
    sig = next(t for t in svc.listar() if t.slug == "signature")
    imagem = svc.definir_fundo_padrao(sig, usuario / "signature" / "backgrounds" / "a.png")
    imagem.unlink()
    sig = next(t for t in svc.listar() if t.slug == "signature")
    executor.responder(["omarchy", "theme", "set", "signature"], "")
    r = svc.aplicar(sig)
    assert r.tema_ok and r.fundo_ok is False and r.pedir_nova_imagem
    assert not any(c[:4] == ("omarchy", "theme", "bg", "set") for c in executor.chamadas)


def test_aplicar_falha_do_tema_nao_mexe_no_fundo(tmp_path, executor, fixtures, monkeypatch):
    svc, *_ = _ambiente(tmp_path, executor, fixtures, monkeypatch)
    tn = next(t for t in svc.listar() if t.slug == "tokyo-night")
    executor.responder(["omarchy", "theme", "set", "tokyo-night"], "", codigo=1, stderr="boom")
    r = svc.aplicar(tn)
    assert not r.tema_ok and "boom" in r.tema_msg and r.fundo_ok is None
