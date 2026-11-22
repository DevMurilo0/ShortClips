"""Small, checksum-verified Portuguese OCR model for local menu detection."""
from pathlib import Path
import hashlib
import json
from urllib.request import urlopen
from .runtime import check_cancelled

TESSDATA=Path(__file__).resolve().parents[1]/'modelos'/'tessdata'
MODEL=TESSDATA/'por.traineddata'
REVISION='87416418657359cb625c412a48b6e1d6d41c29bd'
MODEL_URL=f'https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/{REVISION}/por.traineddata'
SHA256='c4932b937207a9514b7514d518b931a99938c02a28a5a5a553f8599ed58b7deb'


def ensure_model():
    if MODEL.is_file() and hashlib.sha256(MODEL.read_bytes()).hexdigest()==SHA256:
        return TESSDATA
    TESSDATA.mkdir(parents=True,exist_ok=True)
    temporary=MODEL.with_suffix('.download')
    try:
        with urlopen(MODEL_URL,timeout=20) as response,temporary.open('wb') as target:
            while chunk:=response.read(65536):
                check_cancelled();target.write(chunk)
        if hashlib.sha256(temporary.read_bytes()).hexdigest()!=SHA256:
            raise RuntimeError('Checksum do modelo OCR português não corresponde à versão fixada.')
        temporary.replace(MODEL)
    finally:
        temporary.unlink(missing_ok=True)
    return TESSDATA
