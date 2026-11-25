"""Native Android transcription via whisper.cpp; no PyAV or CTranslate2."""
from pathlib import Path
from types import SimpleNamespace
import hashlib
import json
import math
import os
import tempfile

from .runtime import check_cancelled

ROOT = Path(__file__).resolve().parents[1]
MODELS = {
    'tiny': 'bd577a113a864445d4c299885e0cb97d4ba92b5f',
    'base': '465707469ff3a37a2b9b8d8f89f2f99de7299dac',
    'small': '55356645c2b361a969dfd0ef2c5a50d530afd8d5',
}


def cascade_path():
    import cv2
    name = 'haarcascade_frontalface_default.xml'
    data = getattr(getattr(cv2, 'data', None), 'haarcascades', '')
    prefix = Path(os.environ.get('PREFIX', '/usr'))
    candidates = [prefix / 'share/opencv4/haarcascades' / name,
                  prefix / 'share/opencv/haarcascades' / name,
                  ROOT / 'modelos/android' / name]
    if data:
        candidates.insert(0, Path(data) / name)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RuntimeError('Classificador OpenCV ausente. Execute bash instalar-android.sh.')


def digest(path):
    h = hashlib.sha1()
    with path.open('rb') as source:
        while chunk := source.read(1024 * 1024):
            check_cancelled()
            h.update(chunk)
    return h.hexdigest()


def ensure_model(name):
    from .media import run
    if name not in MODELS:
        raise ValueError('Modelo Whisper inválido.')
    folder = ROOT / 'modelos/android'
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / ('ggml-' + name + '.bin')
    if path.is_file() and digest(path) == MODELS[name]:
        return path
    temporary = path.with_suffix('.download')
    try:
        run(['curl', '--fail', '--location', '--retry', '2', '--connect-timeout', '20',
             '--output', str(temporary),
             'https://huggingface.co/ggerganov/whisper.cpp/resolve/main/' + path.name],
            timeout=1800, stage='Baixando modelo de legendas para Android')
        if digest(temporary) != MODELS[name]:
            raise RuntimeError('Checksum do modelo Whisper inválido.')
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def parse_segments(payload):
    """whisper.cpp JSON reports offsets in milliseconds, not seconds."""
    records = payload.get('transcription')
    if not isinstance(records, list):
        raise RuntimeError('Whisper.cpp não retornou uma transcrição válida.')
    result = []
    for record in records:
        check_cancelled()
        try:
            start = float(record['offsets']['from']) / 1000
            end = float(record['offsets']['to']) / 1000
            text = record['text'].strip()
        except (KeyError, TypeError, ValueError, AttributeError) as error:
            raise RuntimeError('Formato da transcrição Whisper.cpp inválido.') from error
        if not math.isfinite(start) or not math.isfinite(end):
            raise RuntimeError('Timestamps inválidos.')
        if start >= 0 and end > start and text:
            result.append(SimpleNamespace(start=start, end=end, text=text, words=None))
    return result


class AndroidWhisper:
    def __init__(self, name):
        self.path = ensure_model(name)
        self.binary = os.environ.get('SHORTFORGE_WHISPER_CLI', 'whisper-cli')

    def transcribe(self, video, language='pt', **kwargs):
        from .media import run
        with tempfile.TemporaryDirectory(prefix='shortforge-whisper-') as directory:
            wav = Path(directory) / 'audio.wav'
            output = Path(directory) / 'transcript'
            run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
                 '-i', str(Path(video).resolve()), '-vn', '-ar', '16000', '-ac', '1',
                 '-c:a', 'pcm_s16le', str(wav)], timeout=180, stage='Preparando áudio')
            run([self.binary, '-m', str(self.path), '-f', str(wav), '-l', language,
                 '-t', '2', '-bs', '2', '-ml', '34', '-sow', '-ng',
                 '-oj', '-of', str(output)], timeout=1800, stage='Transcrevendo no Android')
            file = output.with_suffix('.json')
            if not file.is_file():
                raise RuntimeError('Whisper.cpp não produziu JSON de transcrição.')
            return parse_segments(json.loads(file.read_text(encoding='utf-8'))), None
