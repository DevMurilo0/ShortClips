"""Preflight for the Ubuntu ARM64 userspace in Termux; no downloads or jobs."""
import importlib.metadata as md
import pathlib
import re
import subprocess
import sys

import av
import cv2
import ctranslate2
import numpy
import onnxruntime
from faster_whisper import WhisperModel

def output(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT)

assert av.__version__ == '18.1.0', 'PyAV incompatível'
assert pathlib.Path(cv2.data.haarcascades, 'haarcascade_frontalface_default.xml').is_file()
assert 'int8' in ctranslate2.get_supported_compute_types('cpu'), 'CPU sem suporte a int8'
assert 'CPUExecutionProvider' in onnxruntime.get_available_providers()
assert int(output('node','--version').strip().lstrip('v').split('.')[0]) >= 22
assert re.search(r'\bsubtitles\s+V->V', output('ffmpeg','-hide_banner','-filters'))
assert 'libx264' in output('ffmpeg','-hide_banner','-encoders')
output('ffprobe','-version')
output('tesseract','--version')
for package in ('yt-dlp','yt-dlp-ejs','faster-whisper','ctranslate2','opencv-python-headless','av','numpy','onnxruntime'):
    print(package, md.version(package))
print('Dependências locais OK. A geração de um vídeo real ainda precisa ser testada.')
