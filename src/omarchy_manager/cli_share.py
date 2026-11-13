"""`omarchy-manager share <plugin-ou-tema>` e `omarchy-manager receive`."""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

from omarchy_manager.services import caminhos
from omarchy_manager.services.bundle import (
    ErroBundle,
    aviso_licenca,
    criar_bundle,
    executaveis_em,
    extrair_para_temporario,
    instalar_recebido,
    ler_manifesto_de_pasta,
)
from omarchy_manager.services.lan_share import ErroLan, ServidorEnvio, baixar, codigo_de_confirmacao, descobrir, interpretar_convite
from omarchy_manager.services.omarchy import OmarchyService
from omarchy_manager.services.qr import qr_ansi
from omarchy_manager.services.plugin_catalog import PluginCatalog
from omarchy_manager.services.temas import ThemeService


def _localizar(ident: str) -> tuple[str, str, str, Path, dict]:
    omarchy = OmarchyService()
    catalogo = PluginCatalog()
    for p in catalogo.listar(omarchy.plugin_list_json()):
        if p.id == ident and p.terceiro and p.path is not None:
            return "plugin", p.id, p.name, p.path, dict(versao=p.version, autor=p.author, origem=p.repository_url,
                                                        licenca=ler_manifesto_de_pasta(p.path).get("license", ""))
    for t in ThemeService(omarchy).listar():
        if t.slug == ident and t.do_usuario:
            return "tema", t.slug, t.nome, t.path, dict(origem="")
    raise SystemExit(f"'{ident}' não é um plugin de terceiros nem um tema do usuário. Só esses podem ser compartilhados.")


def share(ident: str) -> int:
    tipo, pid, nome, pasta, meta = _localizar(ident)
    aviso = aviso_licenca(meta.get("licenca", ""))
    if aviso:
        print(f"aviso: {aviso}")
    tmp = Path(tempfile.mkdtemp(prefix="omarchy-manager-bundle-"))
    try:
        arq, man, sha = criar_bundle(tipo, pid, nome, pasta, tmp, **meta)
        print(f"{tipo} {nome}: {len(man.arquivos)} arquivos, {man.tamanho / 1024:.0f} KiB, sha256 {sha}")
        srv = ServidorEnvio(arq, sha)
        s = srv.iniciar()
        try:
            print(f"computador: {s.host}  porta: {s.porta}")
            print(f"código de confirmação: {s.codigo}")
            print(f"convite: {s.convite}")
            qr = qr_ansi(s.convite)
            if qr:
                print(qr)
            print("válido por 10 minutos ou 1 download. Ctrl+C cancela.")
            baixou = srv.esperar()
            print("enviado." if baixou else "encerrado sem envio.")
        finally:
            srv.encerrar()
        return 0 if baixou else 1
    except (ErroBundle, ErroLan) as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\ncancelado.")
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def receive(convite: str | None, instalar: bool) -> int:
    if not convite:
        pares = descobrir()
        if pares:
            print("anunciando na rede local:")
            for p in pares:
                print(f"  {p.nome}  {p.endereco}:{p.porta}  fp {p.fingerprint[:16]}…")
        convite = input("cole o convite (omarchy-manager://…): ").strip()
    try:
        host, porta, fp, segredo = interpretar_convite(convite)
        print(f"código de confirmação: {codigo_de_confirmacao(fp, segredo)}")
        if input("é igual ao do outro computador? [s/N] ").strip().lower() != "s":
            print("cancelado.")
            return 1
        destino_dir = caminhos.DATA_DIR / "recebidos"
        destino_dir.mkdir(parents=True, exist_ok=True)
        arq, sha = baixar(host, porta, fp, segredo, destino_dir / f"recebido-{porta}.omarchy-bundle")
        pasta, man = extrair_para_temporario(arq, sha or None)
    except (ErroLan, ErroBundle, OSError) as exc:
        print(f"recusado: {exc}", file=sys.stderr)
        return 2
    print(f"{man.tipo} {man.nome} ({man.id}) v{man.versao or '?'} de {man.autor or '?'}, licença {man.licenca or '(ausente)'}")
    print(f"{len(man.arquivos)} arquivos, hash conferido. executáveis/código: {', '.join(executaveis_em(pasta)) or 'nenhum'}")
    print(f"pacote: {arq}\nconteúdo extraído em: {pasta}")
    if not instalar:
        print("nada instalado. Use --instalar para copiar (plugin fica DESLIGADO; tema não é aplicado).")
        return 0
    if input("instalar agora? [s/N] ").strip().lower() != "s":
        return 0
    try:
        r = instalar_recebido(pasta, man, confirmado=True)
    except ErroBundle as exc:
        print(f"não instalado: {exc}", file=sys.stderr)
        return 2
    print(f"{r.aviso}\n{r.destino}")
    return 0
