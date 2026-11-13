"""Compartilhamento direto na rede local (plano 10.1, 10.2).

- certificado autoassinado criado por `openssl` para 1 transferência;
- servidor HTTPS em thread, só na interface escolhida (padrão: todas as
  locais, nunca fora da LAN por relay);
- segredo aleatório por envio; 1 download ou 10 minutos;
- fingerprint SHA-256 do certificado no QR e no código de 6 palavras;
- cliente fixa a fingerprint antes de mandar o segredo;
- anúncio mDNS `_omarchy-manager._tcp` por `avahi-publish`, se existir.
"""

from __future__ import annotations

import hashlib
import hmac
import http.client
import http.server
import secrets
import shutil
import socket
import ssl
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from omarchy_manager.services.executor import ComandoAusente, executar
from omarchy_manager.services.log import logger

SERVICO_MDNS = "_omarchy-manager._tcp"
VALIDADE_SEGUNDOS = 600
# 256 palavras curtas em português, sem acento, distintas nas 3 primeiras letras quando possível.
PALAVRAS = (
    "abelha agua aldeia alga alho amora anel anjo arco areia arroz asa ave bacia baile balde bambu banco barco "
    "bola bolo bosque brasa brisa bruma cabo cacau cadeira cafe caixa cama campo cana canoa capa carta casa cedro "
    "ceu chave chuva cinza cobre coco colar colina cometa copo coral corda coruja couro cravo cristal cubo dado "
    "dedo dente deserto disco doce dourado duna eco elmo erva escada escudo esfera espelho estrela farol feira "
    "ferro figo filho flauta flecha flor fogo folha fonte forno fruta fumaca galho garfo gato gelo girassol globo "
    "gota grama grilo gruta harpa hera horta ilha iris jade janela jardim jarro jipe joia junco lago lama lampada "
    "lanterna laranja leao leite lenha lima limao linho livro lobo lua luva maca madeira mala manga mapa mar "
    "marfim mel melao menta mesa milho moinho monte morango musgo nave neve ninho noite noz nuvem oceano olho "
    "onda orvalho ouro ovo palha pao papel parede pato pedra peixe pena pera pinho pipa planta ponte porto prata "
    "prato quadro quartzo queijo quinta raio ramo rede relogio remo rio rocha roda rosa rua sal salsa sapo seda "
    "selo semente serra sino sol sombra sopa tabua taca tambor tapete teia telha tempo terra tigre tinta tocha "
    "topo torre trevo trigo trono tulipa uva vale vela vento verde vidro vila vinho violeta zebra zinco "
    "aipo alce ameixa arara atum baleia bezerro cabra camelo canguru caranguejo carvalho castor cegonha cereja "
    "cisne coelho corvo elefante esquilo faisao foca formiga galo gansa garca girafa golfinho jacare javali "
    "lagosta lesma lontra morcego ovelha panda pavao"
).split()
assert len(PALAVRAS) >= 256, len(PALAVRAS)
PALAVRAS = tuple(PALAVRAS[:256])


class ErroLan(RuntimeError):
    pass


def codigo_de_confirmacao(fingerprint: str, segredo: str) -> str:
    """6 palavras (48 bits) derivadas da fingerprint e do segredo; os 2 lados calculam igual."""
    digest = hmac.new(bytes.fromhex(fingerprint), segredo.encode("utf-8"), hashlib.sha256).digest()
    return " ".join(PALAVRAS[b] for b in digest[:6])


def gerar_certificado(pasta: Path, nome_comum: str = "omarchy-manager") -> tuple[Path, Path, str]:
    """Certificado autoassinado de 1 dia. Devolve (cert, chave, fingerprint sha256 hex)."""
    if shutil.which("openssl") is None:
        raise ErroLan("openssl não encontrado")
    pasta.mkdir(parents=True, exist_ok=True, mode=0o700)
    cert, chave = pasta / "cert.pem", pasta / "key.pem"
    r = executar(["openssl", "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1", "-nodes",
                  "-keyout", str(chave), "-out", str(cert), "-days", "1", "-subj", f"/CN={nome_comum}",
                  "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1"], timeout=30)
    if not r.ok:
        raise ErroLan(f"openssl falhou: {r.erro_legivel}")
    chave.chmod(0o600)
    rf = executar(["openssl", "x509", "-in", str(cert), "-noout", "-fingerprint", "-sha256"], timeout=10)
    if not rf.ok or "=" not in rf.stdout:
        raise ErroLan("não foi possível ler a fingerprint")
    fingerprint = rf.stdout.split("=", 1)[1].strip().replace(":", "").lower()
    return cert, chave, fingerprint


def fingerprint_der(der: bytes) -> str:
    return hashlib.sha256(der).hexdigest()


@dataclass
class SessaoEnvio:
    arquivo: Path
    sha256: str
    host: str
    porta: int
    fingerprint: str
    segredo: str
    expira_em: float
    baixado: bool = False
    cancelado: bool = False

    @property
    def codigo(self) -> str:
        return codigo_de_confirmacao(self.fingerprint, self.segredo)

    @property
    def ativa(self) -> bool:
        return not self.baixado and not self.cancelado and time.monotonic() < self.expira_em

    @property
    def convite(self) -> str:
        """Texto curto para QR Code: host, porta, fingerprint e segredo."""
        return f"omarchy-manager://{self.host}:{self.porta}/{self.fingerprint}/{self.segredo}"


def interpretar_convite(texto: str) -> tuple[str, int, str, str]:
    t = texto.strip()
    prefixo = "omarchy-manager://"
    if not t.startswith(prefixo):
        raise ErroLan("convite inválido")
    resto = t[len(prefixo):]
    try:
        endereco, fingerprint, segredo = resto.split("/", 2)
        host, porta = endereco.rsplit(":", 1)
        return host.strip("[]"), int(porta), fingerprint.lower(), segredo
    except ValueError as exc:
        raise ErroLan("convite inválido") from exc


class _Handler(http.server.BaseHTTPRequestHandler):
    server_version = "omarchy-manager"
    sessao: SessaoEnvio  # definido por subclasse dinâmica

    def log_message(self, *_):  # silencioso; o log vai para o nosso logger
        pass

    def do_GET(self):
        s = self.sessao
        if self.path != "/bundle":
            self.send_error(404)
            return
        if not s.ativa:
            self.send_error(410, "transferencia encerrada")
            return
        auth = self.headers.get("Authorization", "")
        if not hmac.compare_digest(auth, f"Bearer {s.segredo}"):
            logger.warning("lan: segredo incorreto de %s", self.client_address[0])
            self.send_error(403)
            return
        s.baixado = True  # 1 download: marca antes de enviar
        dados = s.arquivo.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(dados)))
        self.send_header("X-Bundle-SHA256", s.sha256)
        self.end_headers()
        self.wfile.write(dados)
        logger.info("lan: pacote enviado para %s", self.client_address[0])


class ServidorEnvio:
    def __init__(self, arquivo: Path, sha256: str, host_anuncio: str | None = None, bind: str = "0.0.0.0",
                 porta: int = 0, publicar_mdns: bool = True) -> None:
        self.arquivo = arquivo
        self.sha256 = sha256
        self._bind = bind
        self._porta = porta
        self._host_anuncio = host_anuncio
        self._publicar = publicar_mdns
        self._tmp = Path(tempfile.mkdtemp(prefix="omarchy-manager-share-"))
        self._httpd: http.server.ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._avahi: subprocess.Popen | None = None
        self.sessao: SessaoEnvio | None = None

    def iniciar(self) -> SessaoEnvio:
        cert, chave, fingerprint = gerar_certificado(self._tmp)
        segredo = secrets.token_urlsafe(24)
        httpd = http.server.ThreadingHTTPServer((self._bind, self._porta), _Handler)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_3
        ctx.load_cert_chain(str(cert), str(chave))
        httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
        porta = httpd.server_address[1]
        host = self._host_anuncio or socket.gethostname()
        self.sessao = SessaoEnvio(self.arquivo, self.sha256, host, porta, fingerprint, segredo,
                                  time.monotonic() + VALIDADE_SEGUNDOS)
        _Handler.sessao = self.sessao
        self._httpd = httpd
        self._thread = threading.Thread(target=httpd.serve_forever, name="omarchy-manager-share", daemon=True)
        self._thread.start()
        if self._publicar:
            self._anunciar(porta, fingerprint)
        logger.info("lan: servindo %s em %s:%d (fp %s)", self.arquivo.name, host, porta, fingerprint[:16])
        return self.sessao

    def _anunciar(self, porta: int, fingerprint: str) -> None:
        exe = shutil.which("avahi-publish")
        if exe is None:
            logger.info("lan: avahi-publish ausente, sem anúncio mDNS")
            return
        nome = f"omarchy-manager em {socket.gethostname()}"
        try:
            self._avahi = subprocess.Popen([exe, "-s", nome, SERVICO_MDNS, str(porta), f"fp={fingerprint}"],
                                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as exc:
            logger.warning("lan: avahi-publish falhou: %s", exc)

    def esperar(self, intervalo: float = 0.2) -> bool:
        """Bloqueia até baixar, cancelar ou expirar. True se baixou."""
        s = self.sessao
        assert s is not None
        while s.ativa:
            time.sleep(intervalo)
        return s.baixado

    def encerrar(self) -> None:
        if self.sessao:
            self.sessao.cancelado = True
            self.sessao.segredo = ""  # invalida o segredo
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        if self._avahi:
            self._avahi.terminate()
            self._avahi = None
        shutil.rmtree(self._tmp, ignore_errors=True)
        logger.info("lan: servidor encerrado e certificado removido")


def baixar(host: str, porta: int, fingerprint_esperada: str, segredo: str, destino: Path, timeout: float = 30.0) -> tuple[Path, str]:
    """Conecta, confere a fingerprint do certificado e só então envia o segredo.
    Devolve (arquivo, sha256 informado pelo servidor)."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE  # a confiança vem da fingerprint fixada abaixo, não de uma CA
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    conn = http.client.HTTPSConnection(host, porta, context=ctx, timeout=timeout)
    try:
        conn.connect()
        der = conn.sock.getpeercert(binary_form=True)  # type: ignore[union-attr]
        if der is None or not hmac.compare_digest(fingerprint_der(der), fingerprint_esperada.lower()):
            raise ErroLan("fingerprint do certificado não confere; conexão recusada")
        conn.request("GET", "/bundle", headers={"Authorization": f"Bearer {segredo}"})
        resp = conn.getresponse()
        if resp.status != 200:
            raise ErroLan(f"servidor respondeu {resp.status} {resp.reason}")
        sha = resp.getheader("X-Bundle-SHA256", "")
        destino.parent.mkdir(parents=True, exist_ok=True)
        with open(destino, "wb") as fh:
            shutil.copyfileobj(resp, fh)
        return destino, sha
    finally:
        conn.close()


@dataclass(frozen=True)
class ParEncontrado:
    nome: str
    host: str
    endereco: str
    porta: int
    fingerprint: str


def descobrir(timeout: float = 3.0) -> list[ParEncontrado]:
    """Lista anúncios `_omarchy-manager._tcp` via avahi-browse. [] sem avahi."""
    exe = shutil.which("avahi-browse")
    if exe is None:
        return []
    try:
        r = executar([exe, "-r", "-t", "-p", SERVICO_MDNS], timeout=timeout + 5)
    except ComandoAusente:
        return []
    pares: list[ParEncontrado] = []
    for linha in r.stdout.splitlines():
        campos = linha.split(";")
        if len(campos) < 10 or campos[0] != "=":
            continue
        nome, host, endereco, porta, txt = campos[3], campos[6], campos[7], campos[8], campos[9]
        fp = ""
        for item in txt.split('" "'):
            item = item.strip('"')
            if item.startswith("fp="):
                fp = item[3:].lower()
        try:
            pares.append(ParEncontrado(nome, host, endereco, int(porta), fp))
        except ValueError:
            continue
    return pares
