import pytest

from omarchy_manager.services import caminhos
from omarchy_manager.services.hyprland import HyprlandService
from omarchy_manager.services.overrides import (
    MARCADOR_LOADER,
    ErroAplicacao,
    ErroOverrides,
    GerenciadorOverrides,
    Override,
    gerar_lua,
    ler_overrides,
    lua_string,
)

A = Override("bind", "super + shift + r", "SSH", "alacritty -e ssh servidor")
B = Override("unbind", "SUPER + SHIFT + B")
C = Override("bind", "SUPER + Q", "Fechar", "hl.dsp.window.close()", kind="lua")


def test_gerar_lua_deterministico():
    assert gerar_lua([A, B, C]) == gerar_lua([C, A, B])


def test_gerar_lua_conteudo():
    texto = gerar_lua([A, B, C])
    assert 'hl.unbind("SUPER + SHIFT + B")' in texto
    assert 'o.bind("SUPER + SHIFT + R", "SSH", "alacritty -e ssh servidor")' in texto
    assert 'hl.bind("SUPER + Q", hl.dsp.window.close(), { description = "Fechar" })' in texto
    # unbinds vêm antes dos binds
    assert texto.index("SUPER + SHIFT + B") < texto.index("SUPER + Q")


def test_round_trip():
    lidos = ler_overrides(gerar_lua([A, B, C]))
    assert {o.combinacao for o in lidos} == {"SUPER + SHIFT + R", "SUPER + SHIFT + B", "SUPER + Q"}
    assert next(o for o in lidos if o.combinacao == "SUPER + Q").kind == "lua"
    assert ler_overrides("-- nada\n") == []


def test_ultimo_override_da_mesma_chave_vence():
    texto = gerar_lua([A, Override("bind", "SUPER+SHIFT+R", "Outro", "foo")])
    assert '"Outro", "foo"' in texto and "ssh" not in texto


def test_escapes():
    assert lua_string('a"b\\c') == '"a\\"b\\\\c"'
    with pytest.raises(ErroOverrides):
        lua_string("a\nb")


@pytest.mark.parametrize(
    "ruim",
    [
        Override("bind", "SUPER + X", "x", "os.execute('rm -rf /')", kind="lua"),
        Override("bind", "SUPER + X", "x", "hl.dsp.exec_cmd('a')\nos.exit()", kind="lua"),
        Override("bind", "SUPER + X", "x", ""),
        Override("bind", "SUPER + X", "x", "echo\nrm"),
        Override("bind", "SUPER", "x", "echo"),
    ],
)
def test_rejeita(ruim):
    with pytest.raises((ErroOverrides, ValueError)):
        gerar_lua([ruim])


@pytest.fixture
def ger(tmp_path, executor, monkeypatch):
    monkeypatch.setattr(caminhos, "PROIBIDOS", (tmp_path / "proibido",))
    monkeypatch.setenv("OMARCHY_PATH", str(tmp_path / "proibido"))
    hypr = tmp_path / "hypr"
    hypr.mkdir()
    (hypr / "bindings.lua").write_text("-- meu bindings\no.bind('SUPER + Z', 'z', 'z')\n")
    executor.responder(["hyprctl", "reload"], "ok")
    executor.responder(["hyprctl", "configerrors"], "\n")
    g = GerenciadorOverrides(
        HyprlandService(executor),
        arquivo=hypr / "omarchy-manager-bindings.lua",
        bindings_usuario=hypr / "bindings.lua",
        pasta_backups=tmp_path / "backups",
        executar_fn=_com_lua_real(executor),
    )
    return g


def _com_lua_real(executor):
    """`lua` roda de verdade (validação sintática); o resto vai ao executor falso."""
    from omarchy_manager.services.executor import executar

    def fn(args, **kw):
        if args[0] == "lua":
            return executar(args, **kw)
        return executor(args, **kw)

    return fn


def test_aplicar_grava_loader_e_backup(ger, executor):
    assert ger.aplicar([A]) is None  # sem arquivo anterior, sem backup
    assert ger.arquivo.is_file() and "SSH" in ger.arquivo.read_text()
    bindings = ger.bindings_usuario.read_text()
    assert bindings.count(MARCADOR_LOADER) == 1 and bindings.startswith("-- meu bindings")
    assert ("hyprctl", "reload") in executor.chamadas and ("hyprctl", "configerrors") in executor.chamadas

    backup = ger.aplicar([A, B])
    assert backup is not None and backup.is_file()
    assert ger.bindings_usuario.read_text().count(MARCADOR_LOADER) == 1
    assert len(ger.atuais()) == 2


def test_retencao_de_20_backups(ger):
    for i in range(25):
        ger.aplicar([Override("bind", f"SUPER + F{i % 12 + 1}", f"n{i}", f"cmd{i}")])
    assert len(ger.backups()) == 20


def test_rollback_quando_hyprland_acusa_erro(ger, executor):
    ger.aplicar([A])
    antes = ger.arquivo.read_text()
    executor.responder(["hyprctl", "configerrors"], "config error in omarchy-manager-bindings.lua: boom\n")
    with pytest.raises(ErroAplicacao) as exc:
        ger.aplicar([A, B])
    assert exc.value.restaurado is False  # a 2ª verificação ainda acusa erro (executor fixo)
    assert ger.arquivo.read_text() == antes
    assert executor.chamadas.count(("hyprctl", "reload")) >= 3


def test_rollback_remove_arquivo_que_nao_existia(ger, executor):
    executor.responder(["hyprctl", "configerrors"], "erro\n")
    with pytest.raises(ErroAplicacao):
        ger.aplicar([A])
    assert not ger.arquivo.exists()


def test_desfazer(ger):
    ger.aplicar([A])
    ger.aplicar([A, B])
    assert len(ger.atuais()) == 2
    ger.desfazer()
    assert len(ger.atuais()) == 1
    assert ger.backups() == []
    with pytest.raises(ErroOverrides):
        ger.desfazer()


def test_nunca_grava_em_caminho_proibido(ger, tmp_path):
    ger.arquivo = tmp_path / "proibido" / "x.lua"
    with pytest.raises(caminhos.CaminhoProibido):
        ger.aplicar([A])
