"""Pacote `.omarchy-bundle` (plano 10.3 a 10.5): criação, validação e importação.

Formato: tar.gz com `bundle.json`, `payload/<arquivos>` e `checksums.sha256`.
Nunca inclui .git, credenciais, caches, logs, backups nem links para fora.
Na importação, plugin fica DESLIGADO e tema vai só para a prévia; nada é
ativado automaticamente.
"""

from __future__ import annotations

import fnmatch
import hashlib
import io
import json
import os
import shutil
import tarfile
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from omarchy_manager.services import caminhos
from omarchy_manager.services.log import logger

VERSAO_FORMATO = 1
EXTENSAO = ".omarchy-bundle"
TIPOS = ("plugin", "tema", "pasta")  # "pasta" é só guardada em Downloads, nunca instalada
LIMITE_TOTAL = 500 * 1024 * 1024
LIMITE_ARQUIVO = 256 * 1024 * 1024
LIMITE_QUANTIDADE = 10_000

EXCLUIR_DIRS = {".git", ".hg", ".svn", "__pycache__", "node_modules", ".cache", "cache", "logs", "backups", ".venv"}
EXCLUIR_PADROES = (
    "*.pem", "*.key", "*.p12", "*.pfx", "id_rsa*", "id_ed25519*", ".env", ".env.*", "*.env",
    "*token*", "*secret*", "*credential*", "*.log", "*.bak", "*.tmp", "*.swp", ".DS_Store",
    "*.lock", "shell.lock.toml", ".netrc", "*.sqlite", "*.db",
)
LICENCAS_LIVRES = {"mit", "apache-2.0", "apache 2.0", "bsd", "bsd-2-clause", "bsd-3-clause", "gpl", "gpl-2.0", "gpl-3.0",
                   "lgpl", "mpl-2.0", "cc0", "cc-by", "cc-by-4.0", "cc-by-sa", "cc-by-sa-4.0", "unlicense", "isc", "0bsd"}


class ErroBundle(ValueError):
    pass


@dataclass(frozen=True)
class ArquivoBundle:
    caminho: str
    tamanho: int
    sha256: str


@dataclass
class Manifesto:
    tipo: str  # plugin | tema | pasta
    id: str
    nome: str
    versao: str = ""
    autor: str = ""
    licenca: str = ""
    origem: str = ""
    tamanho: int = 0
    arquivos: list[ArquivoBundle] = field(default_factory=list)
    formato: int = VERSAO_FORMATO
    criado_em: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2, sort_keys=True)

    @classmethod
    def from_json(cls, texto: str) -> Manifesto:
        try:
            d = json.loads(texto)
        except json.JSONDecodeError as exc:
            raise ErroBundle("bundle.json inválido") from exc
        if not isinstance(d, dict) or d.get("tipo") not in TIPOS:
            raise ErroBundle("bundle.json sem tipo plugin/tema/pasta")
        if not isinstance(d.get("id"), str) or not _id_seguro(d["id"]):
            raise ErroBundle("bundle.json com id inválido")
        arquivos = [ArquivoBundle(**a) for a in d.get("arquivos", []) if isinstance(a, dict)]
        campos = {k: d.get(k, "") for k in ("tipo", "id", "nome", "versao", "autor", "licenca", "origem", "criado_em")}
        return cls(**{k: str(v) for k, v in campos.items()}, tamanho=int(d.get("tamanho", 0)), arquivos=arquivos,
                   formato=int(d.get("formato", 0)))


def _id_seguro(texto: str) -> bool:
    return bool(texto) and len(texto) <= 128 and all(c.isalnum() or c in "._-" for c in texto) and ".." not in texto and not texto.startswith((".", "-"))


def aviso_licenca(licenca: str) -> str | None:
    """Mensagem de aviso, ou None se a licença é conhecida e permite redistribuição."""
    l = licenca.strip().lower()
    if not l:
        return "Licença ausente. O gerenciador não afirma que o compartilhamento é autorizado."
    if l in LICENCAS_LIVRES or any(l.startswith(p) for p in ("mit", "apache", "bsd", "gpl", "lgpl", "mpl", "cc")):
        return None
    return f"Licença '{licenca}' não reconhecida. O gerenciador não afirma que o compartilhamento é autorizado."


def _excluido(rel: Path) -> bool:
    if any(p in EXCLUIR_DIRS for p in rel.parts[:-1]) or rel.name in EXCLUIR_DIRS:
        return True
    return any(fnmatch.fnmatch(rel.name, pad) for pad in EXCLUIR_PADROES)


def listar_arquivos(pasta: Path) -> list[Path]:
    """Arquivos regulares do projeto, já filtrados. Links para fora são ignorados."""
    raiz = pasta.resolve()
    saida: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(raiz):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUIR_DIRS and not (Path(dirpath) / d).is_symlink())
        for nome in sorted(filenames):
            caminho = Path(dirpath) / nome
            rel = caminho.relative_to(raiz)
            if _excluido(rel):
                continue
            if caminho.is_symlink():
                try:
                    alvo = caminho.resolve(strict=True)
                    alvo.relative_to(raiz)
                except (OSError, ValueError):
                    logger.info("bundle: link para fora ignorado: %s", rel)
                    continue
            if not caminho.is_file():
                continue
            saida.append(caminho)
    return saida


def _sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as fh:
        for bloco in iter(lambda: fh.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def sha256_arquivo(caminho: Path) -> str:
    return _sha256(caminho)


def criar_bundle(tipo: str, ident: str, nome: str, pasta: Path, destino_dir: Path, *, versao: str = "", autor: str = "",
                 licenca: str = "", origem: str = "") -> tuple[Path, Manifesto, str]:
    """Gera `<destino_dir>/<id>.omarchy-bundle` e devolve (caminho, manifesto, sha256 do arquivo)."""
    if tipo not in TIPOS:
        raise ErroBundle("tipo deve ser plugin, tema ou pasta")
    if not _id_seguro(ident):
        raise ErroBundle(f"id inválido: {ident!r}")
    raiz = pasta.resolve()
    if not raiz.is_dir():
        raise ErroBundle(f"pasta não existe: {pasta}")
    arquivos = listar_arquivos(raiz)
    if not arquivos:
        raise ErroBundle("nenhum arquivo para empacotar")
    if len(arquivos) > LIMITE_QUANTIDADE:
        raise ErroBundle(f"mais de {LIMITE_QUANTIDADE} arquivos")
    entradas: list[ArquivoBundle] = []
    total = 0
    for a in arquivos:
        tamanho = a.stat().st_size
        if tamanho > LIMITE_ARQUIVO:
            raise ErroBundle(f"arquivo acima de 256 MiB: {a.relative_to(raiz)}")
        total += tamanho
        if total > LIMITE_TOTAL:
            raise ErroBundle("pacote acima de 500 MiB")
        entradas.append(ArquivoBundle(a.relative_to(raiz).as_posix(), tamanho, _sha256(a)))
    manifesto = Manifesto(tipo, ident, nome, versao, autor, licenca, origem, total, entradas, VERSAO_FORMATO,
                          datetime.now().isoformat(timespec="seconds"))
    destino_dir = caminhos.garantir_gravavel(destino_dir)
    destino_dir.mkdir(parents=True, exist_ok=True)
    destino = destino_dir / f"{ident}{EXTENSAO}"
    checksums = "".join(f"{e.sha256}  payload/{e.caminho}\n" for e in entradas)
    fd, tmp = tempfile.mkstemp(dir=destino_dir, prefix=".bundle-", suffix=".tmp")
    os.close(fd)
    try:
        with tarfile.open(tmp, "w:gz") as tar:
            _add_bytes(tar, "bundle.json", manifesto.to_json().encode("utf-8"))
            _add_bytes(tar, "checksums.sha256", checksums.encode("utf-8"))
            for a, e in zip(arquivos, entradas):
                real = a.resolve()  # link interno vira cópia do arquivo, nunca um symlink no tar
                info = tar.gettarinfo(str(real), arcname=f"payload/{e.caminho}")
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                info.mode = 0o755 if info.mode & 0o100 else 0o644
                with open(real, "rb") as fh:
                    tar.addfile(info, fh)
        os.replace(tmp, destino)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    logger.info("bundle criado: %s (%d arquivos, %d bytes)", destino, len(entradas), total)
    return destino, manifesto, _sha256(destino)


def _add_bytes(tar: tarfile.TarFile, nome: str, dados: bytes) -> None:
    info = tarfile.TarInfo(nome)
    info.size = len(dados)
    info.mode = 0o644
    info.mtime = 0
    tar.addfile(info, io.BytesIO(dados))


def _caminho_membro_seguro(nome: str) -> bool:
    if not nome or nome.startswith(("/", "\\")) or "\\" in nome or "\x00" in nome:
        return False
    partes = nome.split("/")
    if any(p in ("", ".", "..") for p in partes):
        return False
    return partes[0] in ("bundle.json", "checksums.sha256", "payload") and (partes[0] != "payload" or len(partes) >= 2)


def validar_bundle(arquivo: Path, sha256_esperado: str | None = None) -> Manifesto:
    """Confere hash do arquivo, estrutura, limites, caminhos e checksums. Não extrai."""
    if sha256_esperado and _sha256(arquivo).lower() != sha256_esperado.lower():
        raise ErroBundle("hash SHA-256 do pacote não confere")
    if arquivo.stat().st_size > LIMITE_TOTAL + (10 << 20):
        raise ErroBundle("pacote acima de 500 MiB")
    try:
        tar = tarfile.open(arquivo, "r:gz")
    except (tarfile.TarError, OSError) as exc:
        raise ErroBundle("pacote não é um tar.gz válido") from exc
    with tar:
        membros = tar.getmembers()
        if len(membros) > LIMITE_QUANTIDADE + 2:
            raise ErroBundle(f"mais de {LIMITE_QUANTIDADE} arquivos")
        nomes = {m.name for m in membros}
        if "bundle.json" not in nomes or "checksums.sha256" not in nomes:
            raise ErroBundle("pacote sem bundle.json ou checksums.sha256")
        total = 0
        for m in membros:
            if not _caminho_membro_seguro(m.name):
                raise ErroBundle(f"caminho rejeitado no pacote: {m.name!r}")
            if m.isdir():
                continue
            if not m.isreg():
                raise ErroBundle(f"entrada não é arquivo regular (link ou especial): {m.name}")
            if m.size > LIMITE_ARQUIVO:
                raise ErroBundle(f"arquivo acima de 256 MiB: {m.name}")
            total += m.size
            if total > LIMITE_TOTAL:
                raise ErroBundle("conteúdo acima de 500 MiB")
        manifesto = Manifesto.from_json(_ler_membro(tar, "bundle.json").decode("utf-8", "replace"))
        if manifesto.formato != VERSAO_FORMATO:
            raise ErroBundle(f"formato de pacote desconhecido: {manifesto.formato}")
        esperados = {f"payload/{a.caminho}": a for a in manifesto.arquivos}
        payload = {m.name: m for m in membros if m.name.startswith("payload/") and m.isreg()}
        if set(payload) != set(esperados):
            raise ErroBundle("lista de arquivos do bundle.json não bate com o conteúdo")
        checks = _ler_membro(tar, "checksums.sha256").decode("utf-8", "replace")
        tabela = {}
        for linha in checks.splitlines():
            partes = linha.split("  ", 1)
            if len(partes) == 2:
                tabela[partes[1]] = partes[0]
        for nome, m in payload.items():
            fh = tar.extractfile(m)
            if fh is None:
                raise ErroBundle(f"não foi possível ler {nome}")
            h = hashlib.sha256()
            for bloco in iter(lambda: fh.read(1 << 20), b""):
                h.update(bloco)
            if h.hexdigest() != esperados[nome].sha256 or tabela.get(nome) != esperados[nome].sha256:
                raise ErroBundle(f"checksum incorreto: {nome}")
            if m.size != esperados[nome].tamanho:
                raise ErroBundle(f"tamanho incorreto: {nome}")
    return manifesto


def _ler_membro(tar: tarfile.TarFile, nome: str) -> bytes:
    fh = tar.extractfile(nome)
    if fh is None:
        raise ErroBundle(f"{nome} ausente")
    return fh.read()


def extrair_para_temporario(arquivo: Path, sha256_esperado: str | None = None) -> tuple[Path, Manifesto]:
    """Valida e extrai só o payload em uma pasta temporária. Devolve (pasta, manifesto)."""
    manifesto = validar_bundle(arquivo, sha256_esperado)
    destino = Path(tempfile.mkdtemp(prefix="omarchy-manager-recebido-"))
    with tarfile.open(arquivo, "r:gz") as tar:
        for m in tar.getmembers():
            if not m.name.startswith("payload/") or not m.isreg():
                continue
            rel = Path(m.name[len("payload/"):])
            alvo = destino / rel
            alvo.parent.mkdir(parents=True, exist_ok=True)
            fh = tar.extractfile(m)
            assert fh is not None
            with open(alvo, "wb") as out:
                shutil.copyfileobj(fh, out)
            os.chmod(alvo, 0o755 if m.mode & 0o100 else 0o644)
    return destino, manifesto


def ler_manifesto_de_pasta(pasta: Path) -> dict:
    try:
        d = json.loads((pasta / "manifest.json").read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def executaveis_em(pasta: Path) -> list[str]:
    saida = []
    for p in sorted(pasta.rglob("*")):
        if p.is_file() and (os.access(p, os.X_OK) or p.suffix in (".sh", ".lua", ".js", ".qml", ".py")):
            saida.append(p.relative_to(pasta).as_posix())
    return saida


@dataclass(frozen=True)
class ResultadoImportacao:
    destino: Path
    backup: Path | None
    aviso: str


def instalar_recebido(pasta_temporaria: Path, manifesto: Manifesto, *, confirmado: bool, substituir: bool = False,
                      raiz_plugins: Path | None = None, raiz_temas: Path | None = None,
                      pasta_backups: Path | None = None) -> ResultadoImportacao:
    """Copia para ~/.config/omarchy/{plugins,themes}/<id>. Nunca liga nem aplica."""
    if not confirmado:
        raise ErroBundle("instalação exige confirmação explícita")
    if manifesto.tipo not in ("plugin", "tema"):
        raise ErroBundle("só plugin e tema podem ser instalados")
    raiz = (raiz_plugins or caminhos.OMARCHY_USER_PLUGINS) if manifesto.tipo == "plugin" else (raiz_temas or caminhos.OMARCHY_USER_THEMES)
    destino = caminhos.garantir_gravavel(raiz / manifesto.id)
    backup = None
    if destino.exists():
        if not substituir:
            raise ErroBundle(f"já existe: {destino}")
        pasta_backups = pasta_backups or caminhos.BACKUPS_DIR
        pasta_backups.mkdir(parents=True, exist_ok=True)
        backup = pasta_backups / f"{manifesto.tipo}-{manifesto.id}.{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        shutil.move(str(destino), str(backup))
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(pasta_temporaria, destino, symlinks=False)
    aviso = ("Plugin instalado DESLIGADO. Revise o manifesto e os executáveis antes de ligar; plugins rodam sem sandbox."
             if manifesto.tipo == "plugin" else "Tema copiado. Nada foi aplicado; use a aba Temas para ver a prévia e aplicar.")
    logger.info("recebido instalado em %s (backup=%s)", destino, backup)
    return ResultadoImportacao(destino, backup, aviso)
