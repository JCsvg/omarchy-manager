"""ThemeService: resolve temas pelos comandos oficiais, lê paletas, acha
fundos, guarda a imagem padrão em config.toml e aplica tema mais fundo."""

from __future__ import annotations

import json
import os
import re
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path

from omarchy_manager.models import Paleta, Tema
from omarchy_manager.services import caminhos
from omarchy_manager.services.log import logger
from omarchy_manager.services.omarchy import ErroOmarchy, OmarchyService, slug_de_nome
from omarchy_manager.services.paleta import ler_paleta

EXTENSOES_IMAGEM = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".mp4", ".webm", ".mkv")


def nome_de_slug(slug: str) -> str:
    """Mesmo `sed` do omarchy-theme-list: "tokyo-night" -> "Tokyo Night"."""
    return " ".join(p[:1].upper() + p[1:] for p in slug.split("-"))


@dataclass(frozen=True)
class ResultadoAplicacao:
    tema_ok: bool
    tema_msg: str
    fundo_ok: bool | None
    fundo_msg: str
    pedir_nova_imagem: bool = False


class ThemeService:
    def __init__(
        self,
        omarchy: OmarchyService | None = None,
        raiz_usuario: Path | None = None,
        raiz_sistema: Path | None = None,
        raiz_fundos_usuario: Path | None = None,
        arquivo_config: Path | None = None,
    ) -> None:
        self.omarchy = omarchy or OmarchyService()
        self.raiz_usuario = raiz_usuario or caminhos.OMARCHY_USER_THEMES
        self.raiz_sistema = raiz_sistema or (caminhos.omarchy_path() / "themes")
        self.raiz_fundos_usuario = raiz_fundos_usuario or caminhos.OMARCHY_USER_BACKGROUNDS
        self.arquivo_config = arquivo_config or caminhos.CONFIG_TOML

    # Descoberta

    def _diretorios(self) -> dict[str, tuple[Path, bool]]:
        mapa: dict[str, tuple[Path, bool]] = {}
        if self.raiz_sistema.is_dir():
            for p in self.raiz_sistema.iterdir():
                if p.is_dir():
                    mapa[p.name] = (p, False)
        if self.raiz_usuario.is_dir():
            for p in self.raiz_usuario.iterdir():
                if p.is_dir() or p.is_symlink():
                    mapa[p.name] = (p, True)
        return mapa

    def fundos_de(self, slug: str, pasta: Path) -> tuple[Path, ...]:
        encontrados: list[Path] = []
        for raiz in (pasta / "backgrounds", self.raiz_fundos_usuario / slug):
            if raiz.is_dir():
                for f in sorted(raiz.iterdir()):
                    if f.is_file() and f.suffix.lower() in EXTENSOES_IMAGEM:
                        encontrados.append(f)
        return tuple(encontrados)

    def listar(self) -> list[Tema]:
        diretorios = self._diretorios()
        try:
            nomes = self.omarchy.theme_list()
        except ErroOmarchy as exc:
            logger.warning("theme list falhou, usando só os diretórios: %s", exc)
            nomes = [nome_de_slug(s) for s in sorted(diretorios)]
        atual = self.omarchy.theme_current_slug()
        padroes = self.fundos_padrao()
        temas: list[Tema] = []
        for nome in nomes:
            slug = slug_de_nome(nome)
            if slug not in diretorios:
                candidatos = [s for s in diretorios if nome_de_slug(s) == nome]
                if not candidatos:
                    logger.info("tema listado sem diretório: %s", nome)
                    continue
                slug = candidatos[0]
            pasta, do_usuario = diretorios[slug]
            paleta: Paleta | None = None
            colors = pasta / "colors.toml"
            if colors.is_file():
                try:
                    paleta = ler_paleta(colors)
                except (OSError, tomllib.TOMLDecodeError):
                    paleta = None
            fundos = self.fundos_de(slug, pasta)
            padrao = padroes.get(slug)
            temas.append(
                Tema(
                    slug=slug,
                    nome=nome,
                    path=pasta,
                    do_usuario=do_usuario,
                    paleta=paleta,
                    fundos=fundos,
                    fundo_padrao=Path(padrao) if padrao else None,
                    atual=(slug == atual),
                )
            )
        return temas

    # Imagem padrão (config.toml)

    def _ler_config(self) -> dict:
        try:
            with open(self.arquivo_config, "rb") as fh:
                return tomllib.load(fh)
        except (OSError, tomllib.TOMLDecodeError):
            return {}

    def fundos_padrao(self) -> dict[str, str]:
        tabela = self._ler_config().get("theme_defaults", {})
        return {str(k): str(v) for k, v in tabela.items()} if isinstance(tabela, dict) else {}

    def _gravar_config(self, dados: dict) -> None:
        destino = caminhos.garantir_gravavel(self.arquivo_config)
        destino.parent.mkdir(parents=True, exist_ok=True)
        linhas = ["# Gerado por omarchy-manager. Edite à vontade; chaves desconhecidas são preservadas.", ""]
        for secao, valores in dados.items():
            if not isinstance(valores, dict):
                linhas.append(f"{_chave_toml(secao)} = {_valor_toml(valores)}")
        for secao, valores in dados.items():
            if isinstance(valores, dict):
                linhas += ["", f"[{secao}]"]
                for k, v in valores.items():
                    linhas.append(f"{_chave_toml(k)} = {_valor_toml(v)}")
        conteudo = "\n".join(linhas) + "\n"
        fd, tmp = tempfile.mkstemp(dir=destino.parent, prefix=".config-", suffix=".toml")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(conteudo)
            tomllib.loads(conteudo)
            os.replace(tmp, destino)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def imagem_permitida(self, tema: Tema, imagem: Path) -> Path | None:
        """Resolve o caminho e só aceita dentro de backgrounds/ do tema ou da
        pasta de fundos do usuário para esse tema (plano, seção 12)."""
        try:
            resolvida = Path(imagem).expanduser().resolve(strict=True)
        except OSError:
            return None
        if not resolvida.is_file() or resolvida.suffix.lower() not in EXTENSOES_IMAGEM:
            return None
        for raiz in (tema.path / "backgrounds", self.raiz_fundos_usuario / tema.slug):
            try:
                resolvida.relative_to(raiz.resolve())
                return resolvida
            except (ValueError, OSError):
                continue
        return None

    def definir_fundo_padrao(self, tema: Tema, imagem: Path | None) -> Path | None:
        dados = self._ler_config()
        tabela = dict(dados.get("theme_defaults", {})) if isinstance(dados.get("theme_defaults"), dict) else {}
        if imagem is None:
            tabela.pop(tema.slug, None)
            resolvida = None
        else:
            resolvida = self.imagem_permitida(tema, imagem)
            if resolvida is None:
                raise ValueError(f"imagem fora das pastas de fundo do tema {tema.slug}: {imagem}")
            tabela[tema.slug] = str(resolvida)
        dados["theme_defaults"] = tabela
        self._gravar_config(dados)
        logger.info("fundo padrão de %s: %s", tema.slug, resolvida)
        return resolvida

    # Aplicação

    def aplicar(self, tema: Tema) -> ResultadoAplicacao:
        r = self.omarchy.theme_set(tema.slug)
        if not r.ok:
            return ResultadoAplicacao(False, f"Falha ao aplicar o tema {tema.nome}: {r.erro_legivel}", None, "")
        tema_msg = f"Tema {tema.nome} aplicado."
        if tema.fundo_padrao is None:
            return ResultadoAplicacao(True, tema_msg, None, "Sem imagem padrão definida; o Omarchy escolheu o fundo.")
        imagem = self.imagem_permitida(tema, tema.fundo_padrao)
        if imagem is None:
            return ResultadoAplicacao(
                True, tema_msg, False, f"A imagem padrão não existe mais: {tema.fundo_padrao}", pedir_nova_imagem=True
            )
        rb = self.omarchy.theme_bg_set(imagem)
        if rb.ok:
            return ResultadoAplicacao(True, tema_msg, True, f"Fundo {imagem.name} aplicado.")
        return ResultadoAplicacao(True, tema_msg, False, f"Falha ao aplicar o fundo {imagem.name}: {rb.erro_legivel}")


def _chave_toml(chave: str) -> str:
    return chave if re.fullmatch(r"[A-Za-z0-9_-]+", chave) else json.dumps(chave, ensure_ascii=False)


def _valor_toml(valor) -> str:
    if isinstance(valor, bool):
        return "true" if valor else "false"
    if isinstance(valor, (int, float)):
        return str(valor)
    if isinstance(valor, list):
        return "[" + ", ".join(_valor_toml(v) for v in valor) + "]"
    return json.dumps(str(valor), ensure_ascii=False)
