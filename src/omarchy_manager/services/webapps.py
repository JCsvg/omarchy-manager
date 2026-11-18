"""Web apps do Omarchy e a conta do Chrome de cada um.

Os web apps são os .desktop em ~/.local/share/applications cujo Exec chama
`omarchy-launch-webapp`. Criar e remover usa `omarchy-webapp-install` e
`omarchy-webapp-remove`. A conta de cada um mora em
~/.config/omarchy-webapps/perfis.conf (`dominio = Profile N`, mais `default = Profile N`),
que o wrapper empacotado em data/omarchy-launch-webapp lê ao abrir o app.
Nada daqui escreve em /usr.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import tomllib
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from omarchy_manager.services import arquivos, caminhos
from omarchy_manager.services.executor import ComandoAusente, executar

COMANDO = "omarchy-launch-webapp"
MARCA_WRAPPER = "# omarchy-manager-wrapper:"
SEM_PADRAO = "default"
ENV_CHROME = "OMARCHY_MANAGER_CHROME_DIR"
ENV_APPS = "OMARCHY_MANAGER_APPS_DIR"
ENV_PERFIS = "OMARCHY_MANAGER_PERFIS"
ENV_BIN = "OMARCHY_MANAGER_BIN_DIR"
ENV_NAVEGADOR = "OMARCHY_MANAGER_NAVEGADOR_PADRAO"


def _xdg(variavel: str, padrao: str) -> Path:
    return Path(os.environ.get(variavel) or Path.home() / padrao)


@dataclass(frozen=True)
class Conta:
    dir: str  # nome da pasta do perfil: Default, Profile 1...
    nome: str
    email: str

    @property
    def rotulo(self) -> str:
        nome = self.nome or self.dir
        return f"{nome} ({self.email})" if self.email else nome

    @property
    def logada(self) -> bool:
        return bool(self.email)


@dataclass(frozen=True)
class Webapp:
    nome: str  # nome do arquivo sem .desktop (é o que omarchy-webapp-remove aceita)
    url: str
    arquivo: Path

    @property
    def dominio(self) -> str:
        return dominio_de(self.url)


# Navegador padrão e ativação da aba

def navegador_padrao(exec_=executar) -> str:
    """Nome do .desktop do navegador padrão (google-chrome.desktop...), ou vazio."""
    forcado = os.environ.get(ENV_NAVEGADOR)
    if forcado is not None:
        return forcado.strip()
    for cmd in (["omarchy-cmd-default-browser"], ["xdg-settings", "get", "default-web-browser"]):
        try:
            r = exec_(cmd, timeout=5)
        except (ComandoAusente, OSError):
            continue
        if r.ok and r.stdout.strip():
            return r.stdout.strip().splitlines()[0].strip()
    return ""


def eh_chrome_ou_chromium(nome: str) -> bool:
    n = nome.strip().lower()
    return n.startswith(("google-chrome", "chromium"))


def dirs_do_navegador(padrao: str = "") -> list[Path]:
    """Pastas candidatas do navegador: a do OMARCHY_MANAGER_CHROME_DIR, ou Chrome e Chromium (o padrão primeiro)."""
    forcada = os.environ.get(ENV_CHROME)
    if forcada:
        return [Path(forcada).expanduser()]
    base = _xdg("XDG_CONFIG_HOME", ".config")
    chrome, chromium = base / "google-chrome", base / "chromium"
    return [chromium, chrome] if padrao.strip().lower().startswith("chromium") else [chrome, chromium]


def ler_contas(padrao: str = "", so_logadas: bool = True) -> tuple[list[Conta], Path | None]:
    """Contas do primeiro `Local State` que existir. Devolve (contas, pasta usada)."""
    for pasta in dirs_do_navegador(padrao):
        arq = pasta / "Local State"
        try:
            dados = json.loads(arq.read_text(encoding="utf-8"))
            cache = dados["profile"]["info_cache"]
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if not isinstance(cache, dict):
            continue
        contas = []
        for dir_, info in cache.items():
            if not isinstance(info, dict):
                continue
            conta = Conta(str(dir_), str(info.get("name") or ""), str(info.get("user_name") or ""))
            if conta.logada or not so_logadas:
                contas.append(conta)
        contas.sort(key=lambda c: (c.dir != "Default", len(c.dir), c.dir))
        return contas, pasta
    return [], None


# Config do app (config.toml, seção [webapps])

def aba_ativa(navegador: str | None = None, arquivo: Path | None = None) -> bool:
    """O que o JC escolheu na aba Config; sem escolha, ativa só se o navegador padrão é Chrome ou Chromium."""
    arq = arquivo or caminhos.CONFIG_TOML
    try:
        with open(arq, "rb") as fh:
            valor = tomllib.load(fh).get("webapps", {}).get("ativa")
    except (OSError, tomllib.TOMLDecodeError, AttributeError):
        valor = None
    if isinstance(valor, bool):
        return valor
    return eh_chrome_ou_chromium(navegador_padrao() if navegador is None else navegador)


def definir_aba_ativa(ativa: bool, arquivo: Path | None = None) -> None:
    from omarchy_manager.services.temas import _chave_toml, _valor_toml

    arq = caminhos.garantir_gravavel(arquivo or caminhos.CONFIG_TOML)
    try:
        with open(arq, "rb") as fh:
            dados = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        dados = {}
    sec = dados.get("webapps")
    sec = dict(sec) if isinstance(sec, dict) else {}
    sec["ativa"] = bool(ativa)
    dados["webapps"] = sec
    linhas = ["# Gerado por omarchy-manager. Edite à vontade; chaves desconhecidas são preservadas.", ""]
    for k, v in dados.items():
        if not isinstance(v, dict):
            linhas.append(f"{_chave_toml(k)} = {_valor_toml(v)}")
    for k, v in dados.items():
        if isinstance(v, dict):
            linhas += ["", f"[{k}]"]
            linhas += [f"{_chave_toml(a)} = {_valor_toml(b)}" for a, b in v.items()]
    texto = "\n".join(linhas) + "\n"
    tomllib.loads(texto)
    arquivos.gravar(arq, texto)


# perfis.conf

def arquivo_perfis() -> Path:
    forcado = os.environ.get(ENV_PERFIS)
    return Path(forcado) if forcado else _xdg("XDG_CONFIG_HOME", ".config") / "omarchy-webapps" / "perfis.conf"


def dominio_de(url: str) -> str:
    """Mesma regra do wrapper: sem esquema, usuário, porta nem "www.", em minúsculas."""
    texto = url.strip()
    host = texto.split("://", 1)[-1]
    host = re.split(r"[/?#]", host, maxsplit=1)[0].rsplit("@", 1)[-1].split(":", 1)[0].lower()
    return host.removeprefix("www.")


def _par(linha: str) -> tuple[str, str] | None:
    """(chave, valor) de uma linha ativa do perfis.conf, ou None (comentário, vazia, desconhecida)."""
    sem = linha.split("#", 1)[0]
    if "=" not in sem:
        return None
    chave, valor = sem.split("=", 1)
    chave, valor = " ".join(chave.split()).removeprefix("www.").lower(), " ".join(valor.split())
    return (chave, valor) if chave and valor else None


class Perfis:
    """perfis.conf em memória. Mantém comentários e linhas que não entende, na ordem em que estavam."""

    def __init__(self, texto: str = "") -> None:
        self.linhas = texto.splitlines()

    @classmethod
    def ler(cls, arquivo: Path | None = None) -> "Perfis":
        try:
            return cls((arquivo or arquivo_perfis()).read_text(encoding="utf-8"))
        except OSError:
            return cls("")

    def mapa(self) -> dict[str, str]:
        saida: dict[str, str] = {}
        for linha in self.linhas:
            p = _par(linha)
            if p and p[0] != SEM_PADRAO:
                saida[p[0]] = p[1]
        return saida

    def padrao(self) -> str:
        valor = ""
        for linha in self.linhas:
            p = _par(linha)
            if p and p[0] == SEM_PADRAO:
                valor = p[1]
        return valor

    def _definir(self, chave: str, perfil: str | None) -> None:
        chave = chave.lower()
        novas, achou = [], False
        for linha in self.linhas:
            p = _par(linha)
            if p and p[0] == chave:
                if perfil and not achou:
                    novas.append(f"{chave} = {perfil}")
                achou = True
                continue  # repetidas somem: o wrapper usa a última, então fica uma só
            novas.append(linha)
        if perfil and not achou:
            novas.append(f"{chave} = {perfil}")
        self.linhas = novas

    def definir(self, dominio: str, perfil: str | None) -> None:
        if not dominio or dominio == SEM_PADRAO:
            raise ValueError("domínio inválido")
        self._definir(dominio.removeprefix("www."), perfil)

    def definir_padrao(self, perfil: str | None) -> None:
        self._definir(SEM_PADRAO, perfil)

    def texto(self) -> str:
        return "\n".join(self.linhas) + "\n" if self.linhas else ""

    def gravar(self, arquivo: Path | None = None) -> Path | None:
        return arquivos.gravar(arquivo or arquivo_perfis(), self.texto())


# Web apps

def dir_apps() -> Path:
    forcado = os.environ.get(ENV_APPS)
    return Path(forcado) if forcado else _xdg("XDG_DATA_HOME", ".local/share") / "applications"


def _campo(texto: str, chave: str) -> str:
    for linha in texto.splitlines():
        if linha.startswith(f"{chave}="):
            return (
                linha.split("=", 1)[1]
                .replace("\\n", "\n").replace("\\t", "\t").replace("\\r", "\r").replace("\\s", " ").replace("\\\\", "\\")
            )
    return ""


def url_do_exec(exec_: str) -> str:
    try:
        partes = shlex.split(exec_)
    except ValueError:
        return ""
    for i, p in enumerate(partes):
        if p.endswith(COMANDO) and i + 1 < len(partes):
            return re.sub(r"\\([`$])", r"\1", partes[i + 1])  # o shlex não desfaz \$ e \` (regra do Exec)
    return ""


def listar(pasta: Path | None = None) -> list[Webapp]:
    pasta = pasta or dir_apps()
    achados = []
    for arq in sorted(pasta.glob("*.desktop"), key=lambda p: p.name.lower()):
        try:
            texto = arq.read_text(encoding="utf-8")
        except OSError:
            continue
        exec_ = _campo(texto, "Exec")
        if COMANDO not in exec_:
            continue
        achados.append(Webapp(arq.stem, url_do_exec(exec_), arq))
    return achados


def normalizar_url(url: str) -> str:
    url = url.strip()
    return url if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", url) else f"https://{url}" if url else ""


def validar_url(url: str) -> str | None:
    """Mensagem de erro, ou None se a URL (já normalizada) serve."""
    if re.search(r"\s", url):
        return "O link não pode ter espaços."
    partes = urlsplit(url)
    if partes.scheme.lower() not in ("http", "https"):
        return "O link precisa começar com http:// ou https://."
    if not partes.hostname:
        return "O link não tem endereço (falta o domínio)."
    return None


def validar_nome(nome: str, existentes: list[Webapp]) -> str | None:
    nome = nome.strip()
    if not nome:
        return "Dê um nome ao web app."
    if "/" in nome or nome.startswith("."):
        return "O nome não pode ter '/' nem começar com ponto."
    if any(c in nome for c in "\n\r\t"):
        return "O nome não pode ter quebra de linha nem tabulação."
    if any(w.nome.lower() == nome.lower() for w in existentes):
        return f"Já existe um web app chamado {nome}."
    return None


def _escapar(valor: str) -> str:
    return valor.replace("\\", "\\\\").replace("\t", "\\t").replace("\r", "\\r").replace("\n", "\\n")


def texto_desktop(nome: str, url: str, icone: str = "") -> str:
    """.desktop no mesmo formato do omarchy-webapp-install (usado quando o comando do Omarchy não existe)."""
    url_exec = url.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$").replace("%", "%%")
    linhas = [
        "[Desktop Entry]", "Version=1.0", f"Name={_escapar(nome)}", f"Comment={_escapar(nome)}",
        f"Exec={_escapar(COMANDO + ' ' + chr(34) + url_exec + chr(34))}",
        "Terminal=false", "Type=Application", f"Icon={_escapar(icone or 'applications-internet')}",
        "StartupNotify=true",
    ]
    return "\n".join(linhas) + "\n"


def criar(nome: str, url: str, icone: str = "", pasta: Path | None = None, exec_=executar) -> tuple[bool, str]:
    """Cria o web app com `omarchy-webapp-install`; se o comando não existe ou falha, grava o .desktop direto."""
    pasta = pasta or dir_apps()
    erro = ""
    if not os.environ.get(ENV_APPS):  # com a pasta trocada, o comando do Omarchy escreveria na real
        try:
            r = exec_(["omarchy-webapp-install", nome, url, icone], timeout=40)
            if r.ok:
                return True, "Criado com omarchy-webapp-install."
            erro = r.erro_legivel
        except (ComandoAusente, OSError) as exc:
            erro = str(exc)
    destino = pasta / f"{nome}.desktop"
    if destino.exists():
        return False, f"Já existe {destino.name}."
    pasta.mkdir(parents=True, exist_ok=True)
    destino.write_text(texto_desktop(nome, url, icone), encoding="utf-8")
    destino.chmod(0o755)
    return True, "Criado direto em .desktop" + (f" (o comando do Omarchy falhou: {erro.splitlines()[0]})" if erro else ".")


def remover(nome: str, exec_=executar) -> tuple[bool, str]:
    """Remove com `omarchy-webapp-remove <nome>` (acha o arquivo pelo nome e apaga só ele e o ícone)."""
    if os.environ.get(ENV_APPS):
        alvo = Path(os.environ[ENV_APPS]) / f"{nome}.desktop"
        if alvo.is_file():
            alvo.unlink()
            return True, "Removido."
        return False, "Arquivo não encontrado."
    try:
        r = exec_(["omarchy-webapp-remove", nome], timeout=20, env={**os.environ, "OMARCHY_REMOVE_NOTIFY": "false"})
    except (ComandoAusente, OSError) as exc:
        return False, str(exc)
    return (True, "Removido.") if r.ok else (False, r.erro_legivel)


# Wrapper omarchy-launch-webapp

def wrapper_empacotado() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / COMANDO


def wrapper_alvo() -> Path:
    forcado = os.environ.get(ENV_BIN)
    return (Path(forcado) if forcado else Path.home() / ".local" / "bin") / COMANDO


def _versao_marca(texto: str) -> int:
    m = re.search(rf"^{re.escape(MARCA_WRAPPER)}\s*(\d+)", texto, re.M)
    return int(m.group(1)) if m else 0


def estado_wrapper() -> tuple[str, str]:
    """(estado, explicação). Estados: ok, ausente, antigo, outro, fora_do_path."""
    alvo = wrapper_alvo()
    try:
        atual = alvo.read_text(encoding="utf-8")
    except OSError:
        return "ausente", f"O wrapper que escolhe a conta não está em {alvo}."
    pacote = wrapper_empacotado().read_text(encoding="utf-8")
    if atual == pacote or (_versao_marca(atual) >= _versao_marca(pacote) > 0):
        achado = shutil.which(COMANDO, path=os.environ.get("PATH", ""))
        if achado is None or Path(achado).resolve() != alvo.resolve():
            return "fora_do_path", f"{alvo} existe, mas {achado or 'nenhum comando'} vem antes no PATH."
        return "ok", "Wrapper ativo."
    if "perfis.conf" in atual and "omarchy-launch-webapp" in atual and "--profile-directory" in atual:
        return "antigo", "O wrapper atual lê o perfis.conf mas não conhece a conta padrão (default)."
    return "outro", f"Já existe um {alvo.name} diferente do empacotado."


def instalar_wrapper() -> Path | None:
    """Grava o wrapper empacotado em ~/.local/bin (com backup do que existia) e devolve o backup."""
    alvo = wrapper_alvo()
    backup = arquivos.gravar(alvo, wrapper_empacotado().read_text(encoding="utf-8"))
    alvo.chmod(0o755)
    return backup
