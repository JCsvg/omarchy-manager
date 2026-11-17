"""Oferta e consulta na rede local (aba Compartilhar).

Quem oferece marca itens (plugin de terceiros, tema do usuário, pasta, arquivo)
e liga um servidor HTTPS. Nada é exposto antes da marcação, e cada conexão só
vê a lista, ou baixa algo, depois de a pessoa que oferece aprovar o IP de quem
conectou. Quem consulta fixa a fingerprint do certificado e mostra o código de
confirmação de 6 palavras, que tem de ser igual nos dois lados.

Sem convite não existe segredo compartilhado: a confiança vem da fingerprint
conferida pelo código (derivado com segredo vazio) mais a aprovação manual.
"""

from __future__ import annotations

import hashlib
import hmac
import http.client
import http.server
import json
import os
import re
import secrets
import shutil
import socket
import ssl
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote, unquote

from omarchy_manager.services import bundle
from omarchy_manager.services.bundle import ErroBundle, criar_bundle, listar_arquivos, sha256_arquivo
from omarchy_manager.services.lan_share import ErroLan, codigo_de_confirmacao, fingerprint_der, gerar_certificado
from omarchy_manager.services.log import logger

VALIDADE_OFERTA = 1800  # 30 minutos
ESPERA_APROVACAO = 60  # segundos que a pessoa tem para aprovar uma conexão


def codigo_do_certificado(fingerprint: str) -> str:
    """Código de 6 palavras só da fingerprint (sem convite, o segredo é vazio)."""
    return codigo_de_confirmacao(fingerprint, "")


# ---------------------------------------------------------------- catálogo


@dataclass(frozen=True)
class ItemOferta:
    id: str
    tipo: str  # plugin | tema | pasta | arquivo
    nome: str
    caminho: Path
    meta: dict = field(default_factory=dict, compare=False)


def _slug(nome: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", nome).strip(".-_")
    return s[:100] or "pasta"


def arquivo_sensivel(caminho: Path) -> bool:
    """Mesma regra do bundle: nome de token, secret, credential, chave, .env etc."""
    return bundle._excluido(Path(caminho.name))


class Catalogo:
    """Itens marcados para oferta. Só o que entra aqui é listado ou enviado."""

    def __init__(self) -> None:
        self._itens: dict[str, ItemOferta] = {}
        self._lock = threading.Lock()
        self._seq = 0

    def _novo(self, tipo: str, nome: str, caminho: Path, meta: dict | None = None) -> ItemOferta:
        with self._lock:
            for i in self._itens.values():
                if i.tipo == tipo and i.caminho == caminho:
                    return i
            self._seq += 1
            item = ItemOferta(str(self._seq), tipo, nome, caminho, meta or {})
            self._itens[item.id] = item
            return item

    def adicionar_plugin(self, ident: str, nome: str, pasta: Path, **meta) -> ItemOferta:
        return self._novo("plugin", nome, self._pasta(pasta), dict(meta, ident=ident))

    def adicionar_tema(self, slug: str, nome: str, pasta: Path, **meta) -> ItemOferta:
        return self._novo("tema", nome, self._pasta(pasta), dict(meta, ident=slug))

    def adicionar_pasta(self, caminho: Path) -> ItemOferta:
        pasta = self._pasta(caminho)
        if not listar_arquivos(pasta):
            raise ErroBundle("a pasta não tem nenhum arquivo que possa ser enviado")
        return self._novo("pasta", pasta.name, pasta, dict(ident=_slug(pasta.name)))

    def adicionar_arquivo(self, caminho: Path) -> ItemOferta:
        p = Path(caminho).expanduser()
        if not p.is_file():
            raise ErroBundle(f"não é um arquivo: {p}")
        p = p.resolve()
        if arquivo_sensivel(p):
            raise ErroBundle(f"{p.name} parece credencial, chave ou segredo e não é enviado")
        return self._novo("arquivo", p.name, p)

    @staticmethod
    def _pasta(caminho: Path) -> Path:
        p = Path(caminho).expanduser()
        if not p.is_dir():
            raise ErroBundle(f"não é uma pasta: {p}")
        return p.resolve()

    def remover(self, item_id: str) -> None:
        with self._lock:
            self._itens.pop(item_id, None)

    def limpar(self) -> None:
        with self._lock:
            self._itens.clear()

    def itens(self) -> list[ItemOferta]:
        with self._lock:
            return list(self._itens.values())

    def obter(self, item_id: str) -> ItemOferta | None:
        with self._lock:
            return self._itens.get(item_id)

    def listagem_publica(self) -> list[dict]:
        """O que o outro lado vê: id, tipo, nome e tamanho. Nunca o caminho local."""
        saida = []
        for i in self.itens():
            try:
                if i.tipo == "arquivo":
                    tamanho, n = i.caminho.stat().st_size, 1
                else:
                    arqs = listar_arquivos(i.caminho)
                    tamanho, n = sum(a.stat().st_size for a in arqs), len(arqs)
            except OSError:
                continue
            saida.append({"id": i.id, "tipo": i.tipo, "nome": i.nome, "tamanho": tamanho, "arquivos": n})
        return saida

    def preparar(self, item: ItemOferta, pasta_tmp: Path) -> tuple[Path, str, str]:
        """Devolve (arquivo a enviar, sha256, nome). Pasta, plugin e tema viram bundle com as exclusões do bundle.py."""
        if item.tipo == "arquivo":
            if arquivo_sensivel(item.caminho):
                raise ErroBundle("arquivo sensível não é enviado")
            return item.caminho, sha256_arquivo(item.caminho), item.caminho.name
        m = item.meta
        arq, _, sha = criar_bundle(item.tipo, m.get("ident") or _slug(item.nome), item.nome, item.caminho, pasta_tmp,
                                   **{k: v for k, v in m.items() if k in ("versao", "autor", "licenca", "origem")})
        return arq, sha, arq.name


# ---------------------------------------------------------------- servidor


class _Handler(http.server.BaseHTTPRequestHandler):
    server_version = "omarchy-manager"

    def log_message(self, *_):
        pass

    @property
    def oferta(self) -> ServidorOferta:
        return self.server.oferta  # type: ignore[attr-defined]

    def _json(self, codigo: int, corpo: dict | list) -> None:
        dados = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def _sessao_ok(self) -> bool:
        if not self.oferta.ativa:
            self.send_error(410, "oferta encerrada")
            return False
        if not self.oferta.sessao_valida(self.headers.get("X-Sessao", ""), self.client_address[0]):
            self.send_error(403, "conexao nao aprovada")
            return False
        return True

    def do_POST(self):
        if self.path != "/conectar":
            self.send_error(404)
            return
        if not self.oferta.ativa:
            self.send_error(410, "oferta encerrada")
            return
        token = self.oferta.pedir_aprovacao(self.client_address[0])
        if token is None:
            self.send_error(403, "conexao recusada")
            return
        self._json(200, {"sessao": token})

    def do_GET(self):
        if self.path == "/lista":
            if self._sessao_ok():
                self._json(200, {"itens": self.oferta.catalogo.listagem_publica()})
            return
        if self.path.startswith("/item/"):
            if not self._sessao_ok():
                return
            item = self.oferta.catalogo.obter(self.path[len("/item/"):])
            if item is None:
                self.send_error(404)
                return
            tmp = Path(tempfile.mkdtemp(prefix="omarchy-manager-oferta-", dir=self.oferta.tmp))
            try:
                arq, sha, nome = self.oferta.catalogo.preparar(item, tmp)
                tamanho = arq.stat().st_size
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(tamanho))
                self.send_header("X-SHA256", sha)
                self.send_header("X-Tipo", item.tipo)
                self.send_header("X-Nome", quote(nome))
                self.end_headers()
                with open(arq, "rb") as fh:
                    shutil.copyfileobj(fh, self.wfile)
                logger.info("oferta: %s %r enviado para %s", item.tipo, item.nome, self.client_address[0])
            except (ErroBundle, OSError) as exc:
                logger.warning("oferta: falha ao preparar %s: %s", item.nome, exc)
                self.send_error(500, "falha ao preparar o item")
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
            return
        self.send_error(404)


class _Httpd(http.server.ThreadingHTTPServer):
    def handle_error(self, request, client_address) -> None:  # sondagens que fecham a conexão não são erro
        logger.info("oferta: conexão de %s encerrada no meio", client_address[0])


class ServidorOferta:
    def __init__(self, catalogo: Catalogo, aprovar: Callable[[str, str], bool], bind: str, porta: int,
                 espera_aprovacao: float = ESPERA_APROVACAO, validade: float = VALIDADE_OFERTA) -> None:
        self.catalogo = catalogo
        self._aprovar = aprovar
        self._bind, self._porta = bind, porta
        self._espera = espera_aprovacao
        self._validade = validade
        self.tmp = Path(tempfile.mkdtemp(prefix="omarchy-manager-oferta-srv-"))
        self._sessoes: dict[str, str] = {}
        self._lock = threading.Lock()
        self._fila = threading.Lock()  # um pedido de aprovação por vez
        self._httpd: http.server.ThreadingHTTPServer | None = None
        self._expira = 0.0
        self._encerrado = False
        self.fingerprint = ""
        self.porta = porta

    @property
    def codigo(self) -> str:
        return codigo_do_certificado(self.fingerprint)

    @property
    def ativa(self) -> bool:
        return not self._encerrado and time.monotonic() < self._expira

    def iniciar(self) -> None:
        cert, chave, self.fingerprint = gerar_certificado(self.tmp / "tls")
        try:
            httpd = _Httpd((self._bind, self._porta), _Handler)
        except OSError as exc:
            self.encerrar()
            raise ErroLan(f"não foi possível escutar em {self._bind}:{self._porta}: {exc.strerror}") from exc
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_3
        ctx.load_cert_chain(str(cert), str(chave))
        httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
        httpd.oferta = self  # type: ignore[attr-defined]
        self.porta = httpd.server_address[1]
        self._httpd = httpd
        self._expira = time.monotonic() + self._validade
        threading.Thread(target=httpd.serve_forever, name="omarchy-manager-oferta", daemon=True).start()
        logger.info("oferta: escutando em %s:%d (fp %s)", self._bind, self.porta, self.fingerprint[:16])

    def pedir_aprovacao(self, ip: str) -> str | None:
        """Pergunta à pessoa que oferece. Devolve o token da sessão, ou None se recusou ou expirou."""
        if not self._fila.acquire(blocking=False):
            logger.info("oferta: %s recusado, outro pedido aguardando resposta", ip)
            return None
        try:
            resultado: list[bool] = []
            t = threading.Thread(target=lambda: resultado.append(bool(self._aprovar(ip, self.codigo))), daemon=True)
            t.start()
            t.join(self._espera)
            if not resultado or not resultado[0] or not self.ativa:
                logger.info("oferta: conexão de %s recusada ou sem resposta", ip)
                return None
            token = secrets.token_urlsafe(24)
            with self._lock:
                self._sessoes[token] = ip
            logger.info("oferta: conexão de %s aprovada", ip)
            return token
        finally:
            self._fila.release()

    def sessao_valida(self, token: str, ip: str) -> bool:
        with self._lock:
            esperado = self._sessoes.get(token, "")
        return bool(token) and bool(esperado) and hmac.compare_digest(esperado, ip)

    def encerrar(self) -> None:
        self._encerrado = True
        with self._lock:
            self._sessoes.clear()
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        shutil.rmtree(self.tmp, ignore_errors=True)
        logger.info("oferta: encerrada, certificado removido")


# ---------------------------------------------------------------- cliente


class ClienteOferta:
    """Lado de quem consulta. Ordem: sondar() -> (a pessoa confere o código) -> autorizar() -> listar() -> baixar()."""

    LIMITE = bundle.LIMITE_TOTAL + (10 << 20)

    def __init__(self, host: str, porta: int, timeout: float = 30.0) -> None:
        self.host, self.porta, self.timeout = host, porta, timeout
        self.fingerprint = ""
        self._sessao = ""

    def _ctx(self) -> ssl.SSLContext:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE  # confiança vem da fingerprint fixada, como em lan_share.baixar
        ctx.minimum_version = ssl.TLSVersion.TLSv1_3
        return ctx

    def _abrir(self, timeout: float | None = None) -> http.client.HTTPSConnection:
        conn = http.client.HTTPSConnection(self.host, self.porta, context=self._ctx(), timeout=timeout or self.timeout)
        try:
            conn.connect()
        except (OSError, ssl.SSLError) as exc:
            conn.close()
            raise ErroLan(f"não foi possível conectar a {self.host}:{self.porta}: {exc}") from exc
        der = conn.sock.getpeercert(binary_form=True)  # type: ignore[union-attr]
        fp = fingerprint_der(der) if der else ""
        if not self.fingerprint:
            self.fingerprint = fp
        elif not hmac.compare_digest(fp, self.fingerprint):
            conn.close()
            raise ErroLan("o certificado mudou desde a conferência do código; conexão recusada")
        return conn

    def sondar(self) -> str:
        """Conecta, anota a fingerprint e devolve o código de 6 palavras. Não envia nada."""
        self.fingerprint = ""
        self._abrir().close()
        return codigo_do_certificado(self.fingerprint)

    def autorizar(self) -> None:
        """Pede a aprovação da outra pessoa (espera até 70 s)."""
        conn = self._abrir(ESPERA_APROVACAO + 10)
        try:
            conn.request("POST", "/conectar")
            r = conn.getresponse()
            corpo = r.read()
            if r.status != 200:
                raise ErroLan("a outra pessoa recusou a conexão" if r.status == 403 else f"servidor respondeu {r.status} {r.reason}")
            self._sessao = json.loads(corpo)["sessao"]
        except (ValueError, KeyError) as exc:
            raise ErroLan("resposta inválida do servidor") from exc
        finally:
            conn.close()

    def _get(self, caminho: str) -> tuple[http.client.HTTPSConnection, http.client.HTTPResponse]:
        conn = self._abrir()
        conn.request("GET", caminho, headers={"X-Sessao": self._sessao})
        r = conn.getresponse()
        if r.status != 200:
            conn.close()
            raise ErroLan(f"servidor respondeu {r.status} {r.reason}")
        return conn, r

    def listar(self) -> list[dict]:
        conn, r = self._get("/lista")
        try:
            itens = json.loads(r.read(1 << 20)).get("itens", [])
        except (ValueError, AttributeError) as exc:
            raise ErroLan("lista inválida") from exc
        finally:
            conn.close()
        ok = []
        for i in itens if isinstance(itens, list) else []:
            if isinstance(i, dict) and str(i.get("id", "")).isdigit() and i.get("tipo") in ("plugin", "tema", "pasta", "arquivo"):
                ok.append({"id": str(i["id"]), "tipo": i["tipo"], "nome": str(i.get("nome", ""))[:200],
                           "tamanho": int(i.get("tamanho", 0) or 0), "arquivos": int(i.get("arquivos", 0) or 0)})
        return ok

    def baixar(self, item_id: str, destino_dir: Path) -> tuple[Path, dict]:
        """Baixa 1 item para uma pasta temporária de trabalho e confere o SHA-256. Devolve (arquivo, meta)."""
        if not str(item_id).isdigit():
            raise ErroLan("id de item inválido")
        conn, r = self._get(f"/item/{item_id}")
        try:
            tipo = r.getheader("X-Tipo", "")
            nome = os.path.basename(unquote(r.getheader("X-Nome", ""))).strip()
            sha = r.getheader("X-SHA256", "").lower()
            if tipo not in ("plugin", "tema", "pasta", "arquivo") or nome in ("", ".", "..") or len(sha) != 64:
                raise ErroLan("cabeçalhos inválidos na resposta")
            destino_dir.mkdir(parents=True, exist_ok=True)
            destino = destino_dir / f"baixando-{item_id}.parte"
            h, total = hashlib.sha256(), 0
            with open(destino, "wb") as fh:
                for bloco in iter(lambda: r.read(1 << 20), b""):
                    total += len(bloco)
                    if total > self.LIMITE:
                        raise ErroLan("item acima de 500 MiB")
                    h.update(bloco)
                    fh.write(bloco)
            if not hmac.compare_digest(h.hexdigest(), sha):
                destino.unlink(missing_ok=True)
                raise ErroLan("SHA-256 do item não confere")
        finally:
            conn.close()
        return destino, {"tipo": tipo, "nome": nome, "sha256": sha}
