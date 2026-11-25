"""Native Termux preflight; exercises FFmpeg and OpenCV on a local synthetic frame."""
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
import numpy
import yt_dlp
from shortforge.android_whisper import cascade_path

def out(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT)

assert not cv2.CascadeClassifier(str(cascade_path())).empty(), 'Cascata facial inválida'
assert int(out('node','--version').strip().lstrip('v').split('.')[0]) >= 22, 'Node >=22 necessário'
assert re.search(r'\bsubtitles\s+V->V',out('ffmpeg','-hide_banner','-filters')), 'FFmpeg sem libass'
assert 'libx264' in out('ffmpeg','-hide_banner','-encoders'), 'FFmpeg sem libx264'
out('ffprobe','-version')
out('tesseract','--version')
assert '-oj' in out(os.environ['SHORTFORGE_WHISPER_CLI'],'--help')
from importlib.metadata import version
print('yt-dlp',version('yt-dlp'),'EJS',version('yt-dlp-ejs'),'OpenCV',cv2.__version__)
with tempfile.TemporaryDirectory() as directory:
    path=Path(directory)/'check.mp4'
    out('ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=blue:s=160x120:r=10',
        '-t','0.5','-c:v','libx264','-threads','2','-pix_fmt','yuv420p',str(path))
    capture=cv2.VideoCapture(str(path))
    try:
        ok,frame=capture.read()
        assert ok and frame.shape[:2]==(120,160), 'OpenCV não decodificou o MP4'
    finally:
        capture.release()
print('Dependências nativas verificadas. Nenhuma tarefa do YouTube foi iniciada.')
