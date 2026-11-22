"""Download, detecção de webcam, legendas e renderização via ferramentas locais."""
from __future__ import annotations

import json
import html
import os
import signal
import tempfile
import textwrap
import unicodedata
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from typing import Callable

from .scoring import clamp
from .runtime import check_cancelled, Cancelled


def require_dependencies():
    missing = [x for x in ('ffmpeg', 'ffprobe', 'tesseract') if not shutil.which(x)]
    if missing:
        raise RuntimeError('Dependências ausentes: '+', '.join(missing)+'. No Arch: sudo pacman -S ffmpeg tesseract')
    try:
        import yt_dlp  # noqa
        import cv2  # noqa
        import numpy  # noqa
    except ImportError as e:
        raise RuntimeError('Dependências Python ausentes. Inicie pelo script ./iniciar.sh.') from e
    from .ocr import ensure_model
    ensure_model()
    checks = run(['ffmpeg', '-hide_banner', '-filters'],timeout=20)
    if not re.search(r'\bsubtitles\s+V->V',checks.stdout):
        raise RuntimeError('Seu FFmpeg não tem suporte a subtitles/libass. Instale a versão completa de ffmpeg.')


def run(cmd: list[str], *, cwd: Path | None = None, stage='Processamento', notify=None, timeout=3600):
    """Bounded subprocess with cancellation and process-group cleanup (including yt-dlp children)."""
    check_cancelled()
    if notify:
        notify(stage)
    process = subprocess.Popen(cmd, cwd=str(cwd) if cwd else None, text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    started = time.monotonic()
    try:
        while True:
            check_cancelled()
            if time.monotonic()-started > timeout:
                raise RuntimeError(f'{stage}: tempo limite de {timeout}s excedido.')
            try:
                stdout, stderr = process.communicate(timeout=.3)
                break
            except subprocess.TimeoutExpired:
                continue
    except BaseException:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass  # Process already exited between the cancellation check and kill.
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
        raise
    if process.returncode:
        err = (stderr or stdout).strip()
        raise RuntimeError(f'{stage}: {err[-4000:] or "erro desconhecido"}')
    return subprocess.CompletedProcess(cmd, process.returncode, stdout, stderr)


def ffprobe(path: Path) -> dict:
    result = run(['ffprobe','-v','error','-show_entries','format=duration:stream=codec_type,width,height,duration,start_time',
                  '-of','json',str(path)])
    data = json.loads(result.stdout)
    video = next((s for s in data.get('streams',[]) if s.get('codec_type')=='video'),{})
    return {
        'duration': float(data.get('format',{}).get('duration',0)),
        'width': int(video.get('width') or 0),
        'height': int(video.get('height') or 0),
        'has_video': bool(video),
        'has_audio': any(x.get('codec_type') == 'audio' for x in data.get('streams', [])),
        'streams': data.get('streams', []),
    }


def metadata_youtube(url, notify):
    notify('Consultando metadados e disponibilidade de Mais reproduzido...')
    result=run([sys.executable,'-m','yt_dlp','--skip-download','--dump-single-json',
        '--no-playlist','--socket-timeout','18','--retries','2',url],stage='Consulta ao YouTube',timeout=120)
    try:
        info=json.loads(result.stdout)
    except ValueError as e:
        raise RuntimeError('O YouTube não retornou metadados válidos. '+result.stderr[-2000:]) from e
    if not info or info.get('_type')=='playlist':
        raise RuntimeError('Envie um vídeo individual acessível, não uma playlist.')
    info['_shortforge_diagnostics']=result.stderr
    return info


def _hook_progress(notify, category):
    last=[0.0]
    def hook(data):
        if data.get('status')=='downloading':
            now=time.monotonic()
            if now-last[0] < 2:
                return
            last[0]=now
            got=data.get('downloaded_bytes') or 0
            total=data.get('total_bytes') or data.get('total_bytes_estimate') or 0
            pct=f' ({got / total * 100:.0f}%)' if total else ''
            notify(category+pct)
        elif data.get('status')=='finished':
            notify(category+' — finalizando arquivo...')
    return hook


def _find_media(folder:Path, stem:str):
    files=[p for p in folder.glob(stem+'.*') if p.suffix.lower() in ('.mp4','.mkv','.webm','.m4a','.opus','.mp3') and p.stat().st_size>0]
    return max(files, key=lambda p:p.stat().st_size) if files else None


def download_audio(url, folder, notify):
    notify('Baixando áudio para análise local...')
    run([sys.executable,'-m','yt_dlp','--no-playlist','--no-progress','--socket-timeout','20',
         '--retries','2','--fragment-retries','2','-f','bestaudio/best',
         '-o',str((folder/'analise_audio.%(ext)s').resolve()),url],stage='Download do áudio',timeout=1800)
    p=_find_media(folder,'analise_audio')
    if not p: raise RuntimeError('Download não produziu áudio válido.')
    return p


def audio_energy(path: Path, duration:float, notify:Callable[[str],None]) -> list[float]:
    import numpy as np
    sample_rate=8000
    cmd=['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-i',str(path),
         '-vn','-ac','1','-ar',str(sample_rate),'-f','f32le','-']
    process=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
    energies=[]
    try:
        while True:
            check_cancelled()
            # Lê o áudio aos poucos: não carrega horas de vídeo na RAM.
            data=process.stdout.read(sample_rate*4)
            if not data:
                break
            arr=np.frombuffer(data, dtype='<f4')
            if len(arr):
                rms=float(np.sqrt(np.mean(np.square(arr.astype(np.float64)))))
                energies.append(math.log1p(50 * rms))
            if len(energies)%180 == 0:
                notify(f'Analisando áudio: {len(energies) // 60} min de {max(1,int(duration // 60))} min')
    except BaseException:
        try:
            os.killpg(process.pid,signal.SIGTERM)
        except ProcessLookupError:
            pass
        raise
    finally:
        if process.stdout:
            process.stdout.close()
        stderr=process.stderr.read().decode('utf-8',errors='replace')
        code=process.wait()
    if code:
        raise RuntimeError('FFmpeg não conseguiu analisar o áudio do vídeo: '+stderr[-2000:])
    if not energies:
        raise RuntimeError('O áudio baixado está vazio.')
    return energies


def timestamp(sec:float):
    if not math.isfinite(sec) or sec < 0:
        raise ValueError('Timestamp inválido')
    ms=round(sec*1000)
    return f'{ms//3600000:02d}:{(ms//60000)%60:02d}:{(ms//1000)%60:02d}.{ms%1000:03d}'


def download_section(url:str, start:float, end:float, work:Path, notify:Callable[[str],None]) -> Path:
    """yt-dlp --download-sections extrai apenas parte do vídeo, sem upload manual."""
    work.mkdir(parents=True,exist_ok=True)
    desired=work/'original.mp4'
    if desired.exists():
        cached=ffprobe(desired)
        if abs(cached['duration']-(end-start)) < .25 and cached['has_audio']:
            return desired
        raise RuntimeError('Trecho existente tem duração incompatível; preserve-o e use outra tarefa.')
    notify(f'Baixando trecho {timestamp(start)}–{timestamp(end)} do YouTube...')
    cmd=[sys.executable,'-m','yt_dlp','--no-playlist','--socket-timeout','20','--retries','2',
         '--download-sections',f'*{timestamp(start)}-{timestamp(end)}',
         '--force-keyframes-at-cuts','--merge-output-format','mp4',
         '--downloader-args','ffmpeg_o:-c:v libx264 -preset veryfast -threads 4',
         '-f','bv*[height<=720]+ba/b[height<=720]/b',
         '--no-progress','-o',str((work/'original.%(ext)s').resolve()),url]
    try:
        run(cmd,stage='Extração do trecho')
    except RuntimeError as e:
        # Não finge sucesso ou contorna medidas de acesso do YouTube.
        raise RuntimeError(f'Falha ao extrair o trecho do YouTube. Verifique se o vídeo está público, se o yt-dlp está atualizado e se o acesso é permitido. Detalhes: {e}') from e
    p=_find_media(work,'original')
    if not p:
        raise RuntimeError('O YouTube não disponibilizou um trecho de vídeo válido.')
    if not 30 <= ffprobe(p)['duration'] <= 60.25:
        raise RuntimeError('O trecho extraído tem menos de 30 segundos. Não será usado.')
    return p


class FacecamNotFound(RuntimeError):
    pass


def identify_facecam(video:Path, corner='auto', manual_box=None):
    """Cluster persistent side-overlay faces, counting unique frames, not detections."""
    import cv2
    import numpy as np
    cap=cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError('Não consegui abrir o trecho para detectar a facecam.')
    try:
        W=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)); H=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        length=cap.get(cv2.CAP_PROP_FRAME_COUNT)/max(cap.get(cv2.CAP_PROP_FPS),1)
        if manual_box is not None:
            x,y,w,h=manual_box
            if not all(math.isfinite(v) for v in manual_box) or not (0<=x<1 and 0<=y<1 and w>0 and h>0 and x+w<=1 and y+h<=1):
                raise ValueError('Retângulo manual fora da imagem.')
            return even_box(x*W,y*H,w*W,h*H,W,H),'Facecam: região definida manualmente pelo usuário'
        corners=('superior-esquerdo','superior-direito','inferior-esquerdo','inferior-direito')
        if corner not in ('auto', *corners):
            raise ValueError('Posição manual da facecam inválida.')
        classifier=cv2.CascadeClassifier(cv2.data.haarcascades+'haarcascade_frontalface_default.xml')
        if classifier.empty():
            raise RuntimeError('Classificador de rostos OpenCV indisponível.')
        clusters=[]; samples=0
        for frame_id,t in enumerate(np.linspace(.5,max(.5,length-.5),12)):
            check_cancelled()
            cap.set(cv2.CAP_PROP_POS_MSEC,float(t)*1000)
            ok,frame=cap.read()
            if not ok: continue
            samples+=1
            scale=min(1,960/max(1,W))
            small=cv2.resize(frame,None,fx=scale,fy=scale) if scale<1 else frame
            gray=cv2.equalizeHist(cv2.cvtColor(small,cv2.COLOR_BGR2GRAY))
            faces=classifier.detectMultiScale(gray,scaleFactor=1.07,minNeighbors=5,minSize=(22,22))
            for x,y,w,h in faces:
                x,y,w,h=[float(z/scale) for z in (x,y,w,h)]
                cx=x+w/2; cy=y+h/2
                # Overlays can be halfway down the side, as in the required video.
                if not (cx/W<.32 or cx/W>.68) or w/W>.22 or h/H>.36: continue
                key=('superior' if cy/H<.5 else 'inferior')+'-'+('esquerdo' if cx/W<.5 else 'direito')
                if corner!='auto' and key!=corner: continue
                match=next((c for c in clusters if abs(cx-c['cx'])<W*.045 and abs(cy-c['cy'])<H*.065
                            and .60<c['w']/w<1.67),None)
                if match is None:
                    match={'cx':cx,'cy':cy,'w':w,'points':[],'frames':set(),'key':key}
                    clusters.append(match)
                match['points'].append((cx,cy,w,h)); match['frames'].add(frame_id)
        best=max(clusters,key=lambda c:len(c['frames']),default=None)
        if best is None or len(best['frames'])<max(4,math.ceil(samples*.45)):
            if corner=='auto':
                raise FacecamNotFound('Facecam não confirmada em amostras persistentes. Veja a prévia e defina a região manual antes de repetir este corte.')
            cw=W*.25; ch=cw*8/9
            x=0 if 'esquerdo' in corner else W-cw
            y=0 if 'superior' in corner else H-ch
            return even_box(x,y,cw,ch,W,H),f'Região manual {corner}; rosto não confirmado'
        cx,cy,fw,fh=np.median(best['points'],axis=0)
        cw=clamp(fw*2.0,W*.13,W*.28)
        ch=cw*8/9
        x=clamp(cx-cw*.5,0,W-cw); y=clamp(cy-ch*.52,0,H-ch)
        return even_box(x,y,cw,ch,W,H),f"Facecam detectada: {best['key']}, persistência {len(best['frames'])}/{samples} quadros"
    finally:
        cap.release()


def even_box(x,y,w,h,W,H):
    w=max(2,min(W,int(w))//2*2)
    h=max(2,min(H,int(h))//2*2)
    x=max(0,min(W-w,int(x))//2*2)
    y=max(0,min(H-h,int(y))//2*2)
    return x,y,w,h


def srt_time(t:float)->str:
    ms=max(0,int(round(t*1000)))
    return f'{ms//3600000:02d}:{(ms//60000)%60:02d}:{(ms//1000)%60:02d},{ms%1000:03d}'


def validate_srt(path:Path, duration=None):
    """Reject missing, malformed, overlapping or out-of-range UTF-8 captions."""
    raw=path.read_text(encoding='utf-8-sig').strip()
    if not raw:
        raise ValueError('Arquivo SRT vazio.')
    cues=[]; previous=0.
    for index,block in enumerate(re.split(r'\n\s*\n',raw),1):
        lines=block.splitlines()
        if len(lines)<3 or lines[0]!=str(index):
            raise ValueError('Índice SRT inválido.')
        match=re.fullmatch(r'(\d{2,}):(\d{2}):(\d{2}),(\d{3}) --> (\d{2,}):(\d{2}):(\d{2}),(\d{3})',lines[1])
        if not match:
            raise ValueError('Timestamp SRT inválido.')
        nums=list(map(int,match.groups()))
        if any(nums[i]>=60 for i in (1,2,5,6)):
            raise ValueError('Timestamp SRT inválido.')
        a=nums[0]*3600+nums[1]*60+nums[2]+nums[3]/1000
        b=nums[4]*3600+nums[5]*60+nums[6]+nums[7]/1000
        if a<previous-.001 or b<=a or (duration is not None and b>duration+.001):
            raise ValueError('Intervalos SRT inválidos ou fora do vídeo.')
        text='\n'.join(lines[2:])
        if not text.strip(): raise ValueError('Legenda sem texto.')
        cues.append((a,b,text)); previous=b
    return cues


def make_srt(model, video:Path, target:Path, notify, language='pt') -> int:
    """Legendas mobile: 2–5 palavras por tela, mantendo o tempo do Whisper."""
    notify('Reconhecendo fala e sincronizando legendas curtas por palavra...')
    duration=ffprobe(video)['duration']
    segments,info=model.transcribe(
        str(video),language=language,vad_filter=True,beam_size=5,
        word_timestamps=True,condition_on_previous_text=False,
        initial_prompt='Transcrição fiel em português brasileiro, com pontuação natural.'
    )
    cues=[]; previous=0.

    def add(start,end,text):
        nonlocal previous
        start=max(previous,0.,float(start));end=min(duration,float(end))
        if end-start < .08 or not text.strip():
            return
        # Não permitir que caracteres interpretados como marcação ASS alterem
        # a renderização. Preferir frases pequenas e no máximo duas linhas.
        text=text.replace('\\','／').replace('{','｛').replace('}','｝')
        lines=textwrap.wrap(text,width=26,break_long_words=True,break_on_hyphens=False)
        cards=[lines[i:i+2] for i in range(0,len(lines),2)]
        total=sum(len(''.join(card)) for card in cards) or 1
        elapsed=start
        for index,card in enumerate(cards):
            ending=end if index==len(cards)-1 else elapsed+(end-start)*len(''.join(card))/total
            if ending-elapsed >= .08:
                cues.append((elapsed,ending,'\n'.join(html.escape(line) for line in card)))
                previous=ending
            elapsed=ending

    for item in segments:
        check_cancelled()
        words=getattr(item,'words',None)
        if words:
            group=[];start=0.;end=0.
            for word in words:
                token=str(word.word).strip()
                if not token:
                    continue
                try:
                    ws,we=float(word.start),float(word.end)
                except (ValueError,TypeError):
                    continue
                if not math.isfinite(ws) or not math.isfinite(we) or we<=ws:
                    continue
                preview=' '.join(group+[token])
                # Ritmo de Shorts: legenda curta, sem texto cobrindo a gameplay.
                if group and (len(group)>=5 or len(preview)>34 or
                              we-start>2.8 or ws-end>.42):
                    add(start,end,' '.join(group))
                    group=[]
                if not group:
                    start=ws
                group.append(token);end=we
                if token.endswith(('.', '?', '!')) or (len(group)>=3 and we-start>=2.4):
                    add(start,end,' '.join(group))
                    group=[]
            if group:
                add(start,end,' '.join(group))
        else:
            # Fallback para modelos sem timestamps: distribuição proporcional
            # por caracteres; nunca fingir sincronização palavra a palavra.
            text=' '.join(str(item.text).split())
            tokens=text.split()
            chunks=[];chunk=[]
            for token in tokens:
                if chunk and (len(chunk)>=5 or len(' '.join(chunk+[token]))>34):
                    chunks.append(' '.join(chunk));chunk=[]
                chunk.append(token)
            if chunk:
                chunks.append(' '.join(chunk))
            elapsed=float(item.start)
            total=sum(len(c) for c in chunks) or 1
            for chunk in chunks:
                ending=elapsed+(float(item.end)-float(item.start))*len(chunk)/total
                add(elapsed,ending,chunk)
                elapsed=ending
    if not cues:
        raise RuntimeError('A transcrição não encontrou fala. Nenhum Short sem legendas será entregue como pronto.')
    target.parent.mkdir(parents=True,exist_ok=True)
    temporary=target.with_suffix('.srt.tmp')
    temporary.write_text(''.join(
        f'{i}\\n{srt_time(a)} --> {srt_time(b)}\\n{text}\\n\\n'
        for i,(a,b,text) in enumerate(cues,1)
    ).replace('\\n','\n'),encoding='utf-8')
    validate_srt(temporary,duration)
    temporary.replace(target)
    return len(cues)


def build_filters(face_box, width):
    if width not in (720,1080): raise ValueError('Resolução inválida.')
    x,y,cw,ch=face_box; half=width*8//9
    # The whole gameplay remains visible; a blurred copy fills the remaining space.
    top=(f'crop={cw}:{ch}:{x}:{y},scale={width}:{half}:force_original_aspect_ratio=increase,'
         f'crop={width}:{half},setsar=1')
    bottom=(f'[b]split=2[bg][fg];[bg]scale={width}:{half}:force_original_aspect_ratio=increase,'
            f'crop={width}:{half},boxblur=20:2[blur];'
            f'[fg]scale={width}:{half}:force_original_aspect_ratio=decrease[game];'
            f'[blur][game]overlay=(W-w)/2:(H-h)/2,setsar=1[bottom];')
    return (f'[0:v]setpts=PTS-STARTPTS,split=2[a][b];[a]{top}[top];'+bottom+
            '[top][bottom]vstack=inputs=2[stack];'
            "[stack]subtitles=filename=captions.srt:charenc=UTF-8:force_style='FontName=DejaVu Sans,Bold=1,"
            f"FontSize={24 if width==720 else 28},PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=3,"
            f"Shadow=1,BorderStyle=1,Alignment=2,MarginV={40 if width==720 else 56},MarginL=22,MarginR=22',format=yuv420p[v]")


def validate_output(path:Path, width=None, decode=True):
    if not path.is_file() or not path.stat().st_size:
        raise RuntimeError('MP4 ausente ou vazio.')
    data=ffprobe(path)
    if not 30 <= data['duration'] <= 60.001:
        raise RuntimeError(f"Duração inválida: {data['duration']:.3f}s (exigido: 30–60s).")
    if not data['has_video'] or not data['has_audio']:
        raise RuntimeError('O MP4 deve conter vídeo e áudio.')
    if data['width']*16!=data['height']*9 or (width and data['width']!=width):
        raise RuntimeError('Resolução de saída inválida: esperado 9:16.')
    streams=data['streams']
    durations=[float(s['duration']) for s in streams if s.get('duration') not in (None,'N/A')]
    starts=[float(s.get('start_time',0)) for s in streams if s.get('start_time') not in (None,'N/A')]
    if (durations and max(durations)-min(durations)>.25) or (starts and max(starts)-min(starts)>.1):
        raise RuntimeError('Duração ou início de áudio/vídeo fora de sincronia.')
    if decode:
        run(['ffmpeg','-v','error','-xerror','-nostdin','-i',str(path.resolve()),'-f','null','-'],
            stage='Validando decodificação completa do MP4')
    return data


def render_split(video:Path, srt:Path, out:Path, face_box, width:int, notify):
    probe=ffprobe(video)
    if not probe['has_audio']: raise RuntimeError('Trecho sem áudio original.')
    if not 30 <= probe['duration'] <= 60.25: raise RuntimeError('Trecho fora do limite de 30–60s.')
    validate_srt(srt,probe['duration'])
    x,y,cw,ch=face_box
    if any(v<0 or v%2 for v in face_box) or cw<2 or ch<2 or x+cw>probe['width'] or y+ch>probe['height']:
        raise ValueError('Região da facecam inválida.')
    out=out.resolve(); out.parent.mkdir(parents=True,exist_ok=True)
    # Static safe filename inside a unique cwd: no path ever enters filter syntax.
    with tempfile.TemporaryDirectory(prefix='render_',dir=srt.resolve().parent) as scratch:
        work=Path(scratch)
        shutil.copyfile(srt.resolve(),work/'captions.srt')
        partial=work/'output.mp4'
        cmd=['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-y','-filter_complex_threads','2',
             '-i',str(video.resolve()),'-filter_complex',build_filters(face_box,width),'-map','[v]',
             '-map','0:a:0','-af','asetpts=PTS-STARTPTS','-t',str(min(60,probe['duration'])),
             '-r','30','-c:v','libx264','-threads','4','-preset','veryfast','-crf','23',
             '-pix_fmt','yuv420p','-c:a','aac','-b:a','128k','-movflags','+faststart',str(partial)]
        run(cmd,cwd=work,notify=notify,stage='Montando facecam, gameplay e legendas...')
        actual=validate_output(partial,width)
        check_cancelled()
        partial.replace(out)
    return actual

class UnsuitableScene(RuntimeError):
    pass


def is_menu_header(text):
    plain=''.join(c for c in unicodedata.normalize('NFKD',text.upper()) if not unicodedata.combining(c))
    words=set(re.findall(r'[A-Z]+',plain))
    if words & {'CONFIGURACOES','HISTORIA'}: return True
    if len(words & {'OPCOES','VOLTAR','COMENTARIOS'})>=2 or {'ROLAR','TELA'}<=words: return True
    return len(words & {'MAPA','REGISTRO','PROGRESSO','JOGADOR','ESTATISTICAS','CONTROLE','JOGABILIDADE','INTERFACE'})>=2


def menu_header_text(frame):
    import cv2
    import numpy as np
    from .ocr import ensure_model
    folder=ensure_model()
    gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
    header=gray[:max(1,int(gray.shape[0]*.23))]
    crop=gray[int(gray.shape[0]*.77):,int(gray.shape[1]*.65):]
    footer=np.full((crop.shape[0],gray.shape[1]),255,dtype=np.uint8)
    footer[:,:crop.shape[1]]=crop
    header=np.vstack((header,footer))
    with tempfile.TemporaryDirectory(prefix='shortforge_ocr_') as scratch:
        path=Path(scratch)/'header.png'
        if not cv2.imwrite(str(path),cv2.resize(header,None,fx=1.5,fy=1.5)):
            raise RuntimeError('Não foi possível criar a amostra OCR.')
        return run(['tesseract',str(path),'stdout','--tessdata-dir',str(folder),
                    '-l','por','--oem','1','--psm','11'],stage='Reconhecendo menus na cena',timeout=20).stdout


def assess_scene(video:Path):
    """Reject persistent screen-within-screen/pillarboxes and nearly static frames.

    Local visual heuristic, not semantic gameplay recognition. Excludes the usual
    side overlays from motion measurement and retains dark, moving gameplay.
    """
    import cv2
    import numpy as np
    cap=cv2.VideoCapture(str(video)); samples=[]; pillarboxed=0; previous=None; motions=[]; menu_frames=[]
    try:
        if not cap.isOpened(): raise RuntimeError('Não foi possível analisar a cena do trecho.')
        duration=cap.get(cv2.CAP_PROP_FRAME_COUNT)/max(1,cap.get(cv2.CAP_PROP_FPS))
        for t in np.linspace(1,max(1,duration-1),10):
            check_cancelled();cap.set(cv2.CAP_PROP_POS_MSEC,float(t)*1000)
            ok,frame=cap.read()
            if not ok:continue
            header=menu_header_text(frame)
            if is_menu_header(header):menu_frames.append(dict(time=round(float(t),3),text=header.strip()))
            gray=cv2.cvtColor(cv2.resize(frame,(320,180)),cv2.COLOR_BGR2GRAY)
            # Both extreme sides must be black for most of the image height.
            left=gray[15:150,:22];right=gray[15:150,-22:]
            if (left<16).mean()>.92 and (right<16).mean()>.55:
                pillarboxed+=1
            center=gray[15:155,65:250]
            if previous is not None:motions.append(float(cv2.absdiff(center,previous).mean()))
            previous=center;samples.append(gray)
    finally:cap.release()
    if len(samples)<5:raise RuntimeError('Quadros insuficientes para analisar a continuidade da cena.')
    metrics={'samples':len(samples),'pillarbox_fraction':pillarboxed/len(samples),
             'mean_motion':float(np.mean(motions)) if motions else 0.,
             'menu_fraction':len(menu_frames)/len(samples),'menu_frames':menu_frames}
    if metrics['menu_fraction']>=.2:
        raise UnsuitableScene(f'Menus/mapa identificados por OCR em {len(menu_frames)}/{len(samples)} quadros; tentando outro momento.')
    if metrics['pillarbox_fraction']>=.6:
        raise UnsuitableScene('Sequência com moldura de tela/vídeo inserido persistente; tentando outro momento com gameplay em tela cheia.')
    if metrics['mean_motion']<.8:
        raise UnsuitableScene('Cena praticamente estática (possível menu/pausa); tentando outro momento.')
    return metrics
