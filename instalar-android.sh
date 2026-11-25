#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ -z "${PREFIX:-}" ] || [ ! -x "$PREFIX/bin/pkg" ]; then
  echo 'Execute no Termux nativo, fora de Ubuntu/PRoot.' >&2; exit 1
fi
if [ "$(uname -m)" != aarch64 ]; then
  echo 'Este perfil foi preparado para Android ARM64.' >&2; exit 1
fi
pkg update
pkg upgrade -y
pkg install -y x11-repo
pkg update
pkg install -y git python python-pip python-numpy opencv-python ffmpeg tesseract nodejs-lts curl cmake clang make ninja fontconfig
python -m venv --system-site-packages .venv-android
.venv-android/bin/python -m pip install 'yt-dlp>=2026.11.23' 'yt-dlp-ejs>=0.8.0'
mkdir -p modelos/android
if ! .venv-android/bin/python -c 'from shortforge.android_whisper import cascade_path; cascade_path()'; then
  tmp=$(mktemp modelos/android/cascade.XXXXXX)
  curl --fail --location --retry 2 -o "$tmp" https://raw.githubusercontent.com/opencv/opencv/4.10.0/data/haarcascades/haarcascade_frontalface_default.xml
  mv "$tmp" modelos/android/haarcascade_frontalface_default.xml
fi
# Build the upstream CLI in Termux with Bionic, not a Linux/glibc binary.
source_dir="$HOME/.local/share/shortforge/whisper.cpp-v1.7.6"
binary="$source_dir/build/bin/whisper-cli"
if [ ! -x "$binary" ]; then
  mkdir -p "$(dirname "$source_dir")"
  if [ ! -d "$source_dir/.git" ]; then
    git clone --depth 1 --branch v1.7.6 https://github.com/ggml-org/whisper.cpp.git "$source_dir"
  fi
  cmake -S "$source_dir" -B "$source_dir/build" -G Ninja -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF -DGGML_NATIVE=OFF -DGGML_OPENMP=OFF -DGGML_BLAS=OFF -DWHISPER_BUILD_TESTS=OFF -DWHISPER_BUILD_EXAMPLES=ON
  cmake --build "$source_dir/build" --target whisper-cli -j 2
fi
# Android's system fonts are accessible without storage permissions.
mkdir -p "$HOME/.config/fontconfig"
if [ ! -f "$HOME/.config/fontconfig/fonts.conf" ]; then
  printf '%s\n' '<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd"><fontconfig><dir>/system/fonts</dir><alias><family>DejaVu Sans</family><prefer><family>sans-serif</family></prefer></alias></fontconfig>' > "$HOME/.config/fontconfig/fonts.conf"
fi
.venv-android/bin/python -c 'from shortforge.android_whisper import ensure_model; ensure_model("tiny")'
bash iniciar-android.sh --check
echo 'Instalação concluída. Execute ./iniciar-android.sh'
