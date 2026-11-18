"""Serviço de web apps: contas do Chrome, perfis.conf, validação, .desktop, wrapper. Tudo em tmp_path."""

import json
import os
import subprocess

import pytest

from omarchy_manager.services import webapps as w
from omarchy_manager.services.executor import Resultado


def _local_state(pasta, perfis):
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "Local State").write_text(json.dumps({"profile": {"info_cache": perfis}}))


def test_contas_so_logadas_e_rotulo(tmp_path, monkeypatch):
    _local_state(tmp_path, {
        "Profile 1": {"name": "Trabalho", "user_name": "trabalho@exemplo.com"},
        "Default": {"name": "Pessoal", "user_name": "pessoal@exemplo.com"},
        "Profile 2": {"name": "Convidado", "user_name": ""},
    })
    monkeypatch.setenv(w.ENV_CHROME, str(tmp_path))
    contas, pasta = w.ler_contas()
    assert pasta == tmp_path
    assert [c.dir for c in contas] == ["Default", "Profile 1"]
    assert contas[0].rotulo == "Pessoal (pessoal@exemplo.com)"
    todas, _ = w.ler_contas(so_logadas=False)
    assert len(todas) == 3 and todas[-1].rotulo == "Convidado"


def test_contas_arquivo_ausente_ou_quebrado(tmp_path, monkeypatch):
    monkeypatch.setenv(w.ENV_CHROME, str(tmp_path / "nada"))
    assert w.ler_contas() == ([], None)
    (tmp_path / "Local State").write_text("{nao e json")
    monkeypatch.setenv(w.ENV_CHROME, str(tmp_path))
    assert w.ler_contas() == ([], None)


def test_dirs_sem_env_usam_chrome_e_chromium(monkeypatch, tmp_path):
    monkeypatch.delenv(w.ENV_CHROME)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert [p.name for p in w.dirs_do_navegador("google-chrome.desktop")] == ["google-chrome", "chromium"]
    assert [p.name for p in w.dirs_do_navegador("chromium.desktop")] == ["chromium", "google-chrome"]


@pytest.mark.parametrize("nome,esperado", [
    ("google-chrome.desktop", True), ("google-chrome-stable.desktop", True), ("chromium.desktop", True),
    ("chromium-browser.desktop", True), ("firefox.desktop", False), ("brave-browser.desktop", False), ("", False),
])
def test_eh_chrome_ou_chromium(nome, esperado):
    assert w.eh_chrome_ou_chromium(nome) is esperado


def test_navegador_padrao_pelos_comandos(monkeypatch, executor):
    monkeypatch.delenv(w.ENV_NAVEGADOR)
    executor.responder(["omarchy-cmd-default-browser"], "chromium.desktop\n")
    assert w.navegador_padrao(executor) == "chromium.desktop"
    executor.respostas.clear()
    executor.responder(["xdg-settings", "get", "default-web-browser"], "google-chrome.desktop\n")
    assert w.navegador_padrao(executor) == "google-chrome.desktop"


def test_ativacao_padrao_e_escolha_persistida(tmp_path):
    cfg = tmp_path / "config.toml"
    assert w.aba_ativa("google-chrome.desktop", cfg) is True
    assert w.aba_ativa("firefox.desktop", cfg) is False
    cfg.write_text('[theme_defaults]\nx = "/a/b.png"\n')
    w.definir_aba_ativa(True, cfg)
    assert w.aba_ativa("firefox.desktop", cfg) is True
    assert 'x = "/a/b.png"' in cfg.read_text()  # o resto do config.toml fica
    w.definir_aba_ativa(False, cfg)
    assert w.aba_ativa("google-chrome.desktop", cfg) is False


def test_perfis_preserva_comentarios_e_linhas_desconhecidas():
    texto = "# cabecalho\nwww.docs.google.com = Profile 1\nlixo sem igual\n# agenda = Profile 9\n"
    p = w.Perfis(texto)
    assert p.mapa() == {"docs.google.com": "Profile 1"}  # "www." ignorado, comentada ignorada
    p.definir("calendar.google.com", "Default")
    p.definir("docs.google.com", "Profile 4")
    p.definir_padrao("Profile 2")
    out = p.texto()
    assert out.startswith("# cabecalho\n") and "lixo sem igual" in out and "# agenda = Profile 9" in out
    assert p.mapa() == {"docs.google.com": "Profile 4", "calendar.google.com": "Default"}
    assert p.padrao() == "Profile 2"
    p.definir("calendar.google.com", None)
    p.definir_padrao(None)
    assert "calendar" not in p.texto() and "default" not in p.texto().lower().replace("# ", "")
    assert p.padrao() == ""


def test_perfis_gravar_com_backup(tmp_path):
    arq = tmp_path / "perfis.conf"
    arq.write_text("# x\n")
    p = w.Perfis.ler(arq)
    p.definir("a.com", "Default")
    backup = p.gravar(arq)
    assert backup is not None and backup.read_text() == "# x\n"
    assert arq.read_text() == "# x\na.com = Default\n"


@pytest.mark.parametrize("url,dom", [
    ("https://www.Docs.google.com/x?y#z", "docs.google.com"), ("http://u@host.com:8080/", "host.com"), ("calendar.google.com", "calendar.google.com"),
])
def test_dominio_de(url, dom):
    assert w.dominio_de(url) == dom


def test_validacao_de_url_e_nome():
    assert w.normalizar_url("calendar.google.com") == "https://calendar.google.com"
    assert w.validar_url("https://a.com/x") is None
    for ruim in ("javascript:alert(1)", "file:///etc/passwd", "ftp://a.com", "https://a b.com", "https://"):
        assert w.validar_url(w.normalizar_url(ruim)), ruim
    existente = [w.Webapp("Docs", "https://docs.google.com", None)]
    assert w.validar_nome("", existente)
    assert w.validar_nome("a/b", existente)
    assert w.validar_nome("docs", existente)  # sem diferenciar maiúsculas
    assert w.validar_nome("Agenda", existente) is None


def test_criar_desktop_listar_e_remover(tmp_path, executor, monkeypatch):
    pasta = tmp_path / "apps"
    monkeypatch.setenv(w.ENV_APPS, str(pasta))
    ok, _ = w.criar("Agenda", "https://calendar.google.com/a?b=1&c=$x", pasta=pasta, exec_=executor)
    assert ok
    texto = (pasta / "Agenda.desktop").read_text()
    assert 'Exec=omarchy-launch-webapp "https://calendar.google.com/a?b=1&c=\\\\$x"' in texto
    (pasta / "Outro.desktop").write_text("[Desktop Entry]\nName=Outro\nExec=foot\n")
    achados = w.listar(pasta)
    assert [a.nome for a in achados] == ["Agenda"]
    assert achados[0].url == "https://calendar.google.com/a?b=1&c=$x" and achados[0].dominio == "calendar.google.com"
    assert executor.chamadas == []  # com a pasta trocada por env, não chama o comando do Omarchy
    ok, _ = w.remover("Agenda", exec_=executor)
    assert ok and not (pasta / "Agenda.desktop").exists()


def test_criar_usa_o_comando_do_omarchy_quando_nao_ha_pasta_trocada(monkeypatch, tmp_path, executor):
    monkeypatch.delenv(w.ENV_APPS)
    executor.responder(["omarchy-webapp-install", "Agenda", "https://a.com", ""], "")
    assert w.criar("Agenda", "https://a.com", pasta=tmp_path, exec_=executor)[0]
    assert executor.chamadas == [("omarchy-webapp-install", "Agenda", "https://a.com", "")]
    executor.respostas.clear()
    executor.responder(["omarchy-webapp-install", "B", "https://b.com", ""], "", codigo=1, stderr="sem icone")
    ok, msg = w.criar("B", "https://b.com", pasta=tmp_path, exec_=executor)  # falhou: cai no .desktop direto
    assert ok and (tmp_path / "B.desktop").exists() and "sem icone" in msg
    executor.respostas.clear()
    executor.responder(["omarchy-webapp-remove", "B"], "")
    assert w.remover("B", exec_=executor)[0]


def _wrapper_em(tmp_path, monkeypatch, conteudo=None):
    bin_ = tmp_path / "bin"
    bin_.mkdir(exist_ok=True)
    monkeypatch.setenv(w.ENV_BIN, str(bin_))
    monkeypatch.setenv("PATH", f"{bin_}:/usr/bin")
    if conteudo is not None:
        (bin_ / w.COMANDO).write_text(conteudo)
        (bin_ / w.COMANDO).chmod(0o755)
    return bin_ / w.COMANDO


def test_estados_do_wrapper(tmp_path, monkeypatch):
    alvo = _wrapper_em(tmp_path, monkeypatch)
    assert w.estado_wrapper()[0] == "ausente"
    _wrapper_em(tmp_path, monkeypatch, "#!/bin/bash\necho meu\n")
    assert w.estado_wrapper()[0] == "outro"
    antigo = '#!/bin/bash\n# perfis.conf\norig=/usr/share/omarchy/bin/omarchy-launch-webapp\nargs+=("--profile-directory=$p")\n'
    _wrapper_em(tmp_path, monkeypatch, antigo)
    assert w.estado_wrapper()[0] == "antigo"
    backup = w.instalar_wrapper()
    assert backup is not None and backup.read_text() == antigo
    assert alvo.read_text() == w.wrapper_empacotado().read_text()
    assert os.access(alvo, os.X_OK)
    assert w.estado_wrapper()[0] == "ok"
    monkeypatch.setenv("PATH", "/usr/bin")
    assert w.estado_wrapper()[0] == "fora_do_path"


def test_wrapper_do_jc_atual_e_reconhecido_como_antigo_sem_duplicar():
    """O wrapper que o JC já tem (sem default) é equivalente ao empacotado para domínios; só falta o default."""
    pacote = w.wrapper_empacotado().read_text()
    assert pacote.startswith("#!/bin/bash\n# omarchy-manager-wrapper: 2")
    assert "--profile-directory=" in pacote and "OMARCHY_WEBAPP_DRY" in pacote


def _dry(tmp_path, url, conf):
    cfg = tmp_path / "xdg" / "omarchy-webapps"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "perfis.conf").write_text(conf)
    env = {**os.environ, "XDG_CONFIG_HOME": str(tmp_path / "xdg"), "OMARCHY_WEBAPP_DRY": "1"}
    return subprocess.run([str(w.wrapper_empacotado()), url], env=env, capture_output=True, text=True, check=True).stdout.strip()


def test_wrapper_empacotado_mapeado_padrao_e_original(tmp_path):
    conf = "# c\nwww.docs.google.com = Profile 1\ndefault = Profile 2\n"
    assert "--profile-directory=Profile\\ 1" in _dry(tmp_path, "https://docs.google.com/d", conf)
    assert "--profile-directory=Profile\\ 2" in _dry(tmp_path, "https://outro.com", conf)
    sem_padrao = _dry(tmp_path, "https://outro.com", "docs.google.com = Profile 1\n")
    assert "--profile-directory" not in sem_padrao and sem_padrao.startswith("/usr/share/omarchy/bin/omarchy-launch-webapp")
    assert "--profile-directory" not in _dry(tmp_path, "https://outro.com", "")
