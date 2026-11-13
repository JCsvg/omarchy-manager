import json

import pytest

from omarchy_manager.models import Atalho
from omarchy_manager.services.plugin_catalog import (
    PluginCatalog,
    atalhos_do_plugin,
    ler_aliases,
    ler_manifesto,
    normalizar_url_repositorio,
)


@pytest.mark.parametrize(
    "bruta, esperada",
    [
        ("https://github.com/NIPSEN/omarchy-dell-power.git", "https://github.com/NIPSEN/omarchy-dell-power"),
        ("https://github.com/a/b", "https://github.com/a/b"),
        ("https://github.com/a/b/", "https://github.com/a/b"),
        ("git@github.com:a/b.git", "https://github.com/a/b"),
        ("ssh://git@gitlab.com/a/b.git", "https://gitlab.com/a/b"),
        ("git://codeberg.org/a/b", "https://codeberg.org/a/b"),
        ("http://github.com/a/b", ""),
        ("https://exemplo.com/a/b", ""),
        ("https://github.com/so-usuario", ""),
        ("file:///etc/passwd", ""),
        ("rm -rf /", ""),
        ("", ""),
    ],
)
def test_normalizacao_url(bruta, esperada):
    assert normalizar_url_repositorio(bruta) == esperada


def _raizes(tmp_path):
    sistema = tmp_path / "sistema"
    usuario = tmp_path / "usuario"
    (sistema / "clipboard").mkdir(parents=True)
    (sistema / "clipboard" / "manifest.json").write_text(
        json.dumps({"id": "omarchy.clipboard", "name": "Clipboard", "version": "1.0.0", "author": "Omarchy", "description": "Histórico"})
    )
    (sistema / "bar").mkdir()
    (sistema / "bar" / "manifest.json").write_text(json.dumps({"id": "omarchy.bar", "name": "Bar"}))
    dell = usuario / "io.github.nipsen.dell-power"
    dell.mkdir(parents=True)
    (dell / "manifest.json").write_text(
        json.dumps({"id": "io.github.nipsen.dell-power", "name": "Dell Power", "version": "1.4.1", "author": "NIPSEN", "description": "Bateria"})
    )
    (dell / ".git").mkdir()
    lock = usuario / "bibek.lock"
    lock.mkdir()
    (lock / "manifest.json").write_text("{quebrado")
    return sistema, usuario


def test_catalogo_monta_plugins(tmp_path, executor, fixtures):
    sistema, usuario = _raizes(tmp_path)
    executor.responder(
        ["git", "-C", str(usuario / "io.github.nipsen.dell-power"), "remote", "get-url", "origin"],
        "git@github.com:NIPSEN/omarchy-dell-power.git\n",
    )
    cat = PluginCatalog(executor, raiz_usuario=usuario, raiz_sistema=sistema, traducoes={})
    plugins = {p.id: p for p in cat.listar(json.loads((fixtures / "plugin_list.json").read_text()))}

    clip = plugins["omarchy.clipboard"]
    assert clip.first_party and not clip.desinstalavel and clip.description == "Histórico"
    assert clip.metadados_incompletos == ()

    bar = plugins["omarchy.bar"]
    assert not bar.can_disable
    assert set(bar.metadados_incompletos) == {"description", "author", "version"}

    dell = plugins["io.github.nipsen.dell-power"]
    assert dell.terceiro and dell.desinstalavel
    assert dell.repository_url == "https://github.com/NIPSEN/omarchy-dell-power"
    assert dell.version == "1.4.1"

    lock = plugins["bibek.lock"]
    assert lock.metadados_incompletos == ("manifest.json",)
    assert lock.repository_url == ""

    fantasma = plugins["sem.pasta"]
    assert fantasma.path is None and not fantasma.desinstalavel
    assert "pasta do plugin" in fantasma.metadados_incompletos


def test_manifesto_url_no_manifesto_tem_prioridade(tmp_path, executor):
    pasta = tmp_path / "p"
    pasta.mkdir()
    (pasta / "manifest.json").write_text(json.dumps({"id": "x.y", "repository": {"url": "https://github.com/x/y.git"}}))
    cat = PluginCatalog(executor, raiz_usuario=tmp_path, raiz_sistema=tmp_path / "nada")
    dados, _ = ler_manifesto(pasta)
    assert cat.url_repositorio(pasta, dados) == "https://github.com/x/y"
    assert executor.chamadas == []


def test_aliases(tmp_path):
    arq = tmp_path / "plugin-shortcuts.toml"
    arq.write_text('[aliases]\n"a.b" = ["omarchy-ab", "ab-panel"]\n"c.d" = "cd"\n')
    assert ler_aliases(arq) == {"a.b": ["omarchy-ab", "ab-panel"], "c.d": ["cd"]}
    assert ler_aliases(tmp_path / "inexistente.toml") == {}


def test_associacao_de_atalhos():
    atalhos = [
        Atalho(68, "V", description="Clipboard", comando="omarchy-shell shell toggle omarchy.clipboard"),
        Atalho(68, "E", description="Emojis", comando="omarchy-shell shell toggle 'omarchy.emojis'"),
        Atalho(64, "P", description="Pomodoro", comando="omarchy-shell -q shell togglePanel mlhunter.pomodoro"),
        Atalho(64, "X", description="Alias", comando="/home/jc/.local/bin/pomo-start"),
        Atalho(64, "Y", description="Lua opaco", dispatcher="__lua", arg="12"),
        Atalho(64, "Z", description="Marcado", plugin_id="mlhunter.pomodoro"),
    ]
    assert [a.key for a in atalhos_do_plugin("omarchy.clipboard", atalhos)] == ["V"]
    assert [a.key for a in atalhos_do_plugin("omarchy.emojis", atalhos)] == ["E"]
    assert [a.key for a in atalhos_do_plugin("mlhunter.pomodoro", atalhos, {"mlhunter.pomodoro": ["pomo-start"]})] == ["P", "X", "Z"]
    assert atalhos_do_plugin("nao.existe", atalhos) == []
