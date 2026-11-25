#!/usr/bin/env bash
# Execute inside Ubuntu 24.04 ARM64 (PRoot), not in native Termux.
set -euo pipefail
cd "$(dirname "$0")"
if [ "$(uname -m)" != aarch64 ] || [ ! -f /etc/os-release ]; then
  echo 'Use Ubuntu ARM64 dentro do Termux (veja docs/TERMUX.md).' >&2; exit 1
fi
. /etc/os-release
if [ "$ID" != ubuntu ] || [ "$VERSION_ID" != 24.04 ]; then
  echo 'Este instalador requer Ubuntu 24.04 ARM64 via PRoot.' >&2; exit 1
fi
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends python3 python3-venv python3-pip ffmpeg tesseract-ocr ca-certificates curl xz-utils libgomp1 libstdc++6 fonts-dejavu-core fonts-liberation
node_dir="$HOME/.local/share/shortforge/node-v22.23.5"
if [ ! -x "$node_dir/bin/node" ]; then
  tmp=$(mktemp -d)
  trap 'rm -rf "$tmp"' EXIT
  curl --fail --location --retry 2 --output "$tmp/node.tar.xz" https://nodejs.org/dist/v22.23.5/node-v22.23.5-linux-arm64.tar.xz
  printf '%s  %s\n' '2babb9eb5264860d540849f4b064a6fbdebcdc323657d9d382ce23d313fd5e09' "$tmp/node.tar.xz" | sha256sum -c -
  mkdir -p "$node_dir"
  tar -xJf "$tmp/node.tar.xz" --strip-components=1 -C "$node_dir"
fi
"$node_dir/bin/node" --version
python3 -m venv .venv-termux
.venv-termux/bin/python -m pip install --upgrade pip
.venv-termux/bin/python -m pip install --prefer-binary --only-binary=opencv-python-headless,numpy,av,ctranslate2,onnxruntime,tokenizers -r requirements-termux.txt
.venv-termux/bin/python -m pip check
./iniciar-termux.sh --check
echo 'Instalacao concluida. Execute ./iniciar-termux.sh'
