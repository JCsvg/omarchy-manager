#!/usr/bin/env bash
# Gera o tarball a partir do git e constrói o pacote com makepkg.
#
#   packaging/empacotar.sh            constrói (e roda namcap, se existir)
#   packaging/empacotar.sh --instalar constrói e instala com pacman -U
#
# Tudo acontece dentro de packaging/; nada toca /usr/share/omarchy.
set -euo pipefail

aqui=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
raiz=$(cd "$aqui/.." && pwd)
pkgver=$(sed -n 's/^pkgver=//p' "$aqui/PKGBUILD")
nome="omarchy-manager-$pkgver"
tarball="$aqui/$nome.tar.gz"

# A árvore versionada, mais o LICENSE se ainda não estiver no commit.
git -C "$raiz" archive --format=tar --prefix="$nome/" HEAD | gzip -n >"$tarball"
echo "tarball: $tarball"
echo "sha256:  $(sha256sum "$tarball" | cut -d' ' -f1)"

cd "$aqui"
rm -rf src pkg
makepkg -f --cleanbuild "$@"

if command -v namcap >/dev/null; then
  echo "--- namcap"
  namcap PKGBUILD || true
  namcap "$aqui"/omarchy-manager-"$pkgver"-*.pkg.tar.* || true
fi
