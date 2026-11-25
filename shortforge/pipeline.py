"""Durable local jobs: selection, isolated clips, cancellation and selective retry."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import copy
import json
import math
import os
import re
import threading
import zipfile

from .media import (require_dependencies, metadata_youtube, download_audio, audio_energy,
                    download_section, identify_facecam, make_srt, render_split, ffprobe, assess_scene, UnsuitableScene)
from .scoring import extract_heatmap, pick_segments
from .runtime import cancel_event, check_cancelled, Cancelled


def validate_url(raw:str)->str:
    parsed=urlparse(raw.strip())
    host=(parsed.hostname or '').lower()
    valid=host in {'youtu.be','youtube.com','www.youtube.com','m.youtube.com','music.youtube.com'}
    if parsed.scheme not in ('https','http') or not valid or parsed.username or parsed.password or parsed.port not in (None,80,443):
        raise ValueError('Cole um link válido de um vídeo do YouTube.')
    if host=='youtu.be':
        video_id=parsed.path.strip('/')
    elif parsed.path=='/watch':
        video_id=parse_qs(parsed.query).get('v',[''])[0]
    else:
        match=re.fullmatch(r'/(?:shorts|live)/([A-Za-z0-9_-]{11})/?',parsed.path)
        video_id=match[1] if match else ''
    if not re.fullmatch(r'[A-Za-z0-9_-]{11}',video_id):
        raise ValueError('O link deve conter o identificador de um vídeo individual (11 caracteres).')
    return 'https://youtu.be/'+video_id


def validate_manual_box(value):
    if value is None or value==[]: return None
    if not isinstance(value,list) or len(value)!=4 or any(isinstance(v,bool) for v in value):
        raise ValueError('Região manual: informe [x, y, largura, altura] em porcentagens de 0 a 100.')
    box=[float(v)/100 for v in value]
    x,y,w,h=box
    if not all(math.isfinite(v) for v in box) or not (0<=x<1 and 0<=y<1 and w>0 and h>0 and x+w<=1 and y+h<=1):
        raise ValueError('A região manual deve caber na imagem (0–100%).')
    return box


@dataclass
class Job:
    id:str
    url:str
    count:int
    length:int
    resolution:int
    facecam:str
    model_name:str
    destination:Path
    status:str='queued'
    stage:str='queued'
    message:str='Aguardando início...'
    progress:int=0
    title:str=''
    selection_mode:str=''
    clips:list[dict]=field(default_factory=list)
    errors:list[str]=field(default_factory=list)
    zip_name:str|None=None
    candidates:list[dict]=field(default_factory=list)
    manual_box:list|None=None
    started_at:str=field(default_factory=lambda:datetime.now(timezone.utc).isoformat())
    lock:threading.RLock=field(default_factory=threading.RLock,repr=False)
    cancel:threading.Event=field(default_factory=threading.Event,repr=False)

    def update(self,message,progress=None,stage=None):
        check_cancelled()
        with self.lock:
            self.message=message
            if progress is not None: self.progress=round(100*sum(c.get('status')=='ready' for c in self.clips)/max(1,self.count))
            if stage: self.stage=stage
            self.persist()

    def asdict(self):
        with self.lock:
            return copy.deepcopy(dict(id=self.id,url=self.url,count=self.count,length=self.length,
                resolution=self.resolution,facecam=self.facecam,model_name=self.model_name,
                status=self.status,stage=self.stage,message=self.message,progress=self.progress,
                title=self.title,selection_mode=self.selection_mode,clips=self.clips,errors=self.errors,
                zip_name=self.zip_name,candidates=self.candidates,manual_box=self.manual_box,started_at=self.started_at))

    def persist(self):
        with self.lock:
            self.destination.mkdir(parents=True,exist_ok=True)
            temporary=self.destination/'tarefa.json.tmp'
            temporary.write_text(json.dumps(self.asdict(),ensure_ascii=False,indent=2),encoding='utf-8')
            temporary.replace(self.destination/'tarefa.json')


def restore_jobs(root):
    jobs={}
    for path in sorted(root.glob('*/tarefa.json'),key=lambda p:p.stat().st_mtime):
        try:
            data=json.loads(path.read_text(encoding='utf-8'))
            job=Job(**data,destination=path.parent)
            if job.id!=path.parent.name: raise ValueError('Identificador divergente')
            if job.status in ('queued','running','cancelling'):
                job.status='failed'; job.stage='failed'
                job.message='Servidor interrompido. Repita os cortes pendentes.'
                for clip in job.clips:
                    if clip['status']!='ready': clip.update(status='failed',error=job.message)
                job.errors.append(job.message); job.persist()
            jobs[job.id]=job
        except (ValueError,TypeError,OSError) as e:
            print(f'Não foi possível restaurar {path}: {e}')
    return jobs


def _load_whisper(model_name):
    try:
        if os.getenv('SHORTFORGE_ANDROID_NATIVE')=='1':
            from .android_whisper import AndroidWhisper
            return AndroidWhisper(model_name)
        from faster_whisper import WhisperModel
        # Bound CPU use; leave the interface and cancellation responsive.
        return WhisperModel(model_name,device='cpu',compute_type='int8',cpu_threads=2 if os.getenv('SHORTFORGE_TERMUX')=='1' else 4,num_workers=1)
    except Exception as e:
        raise RuntimeError('Não foi possível carregar o modelo de legendas. Verifique as dependências e o acesso ao modelo na primeira execução. '+str(e)) from e


def _finish(job):
    """Rebuild ZIP atomically from ready clips only; preserve every valid MP4."""
    check_cancelled()
    report={'video':job.title,'source':job.url,'method':job.selection_mode,
            'generated':datetime.now(timezone.utc).isoformat(),'clips':copy.deepcopy(job.clips)}
    (job.destination/'relatorio.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    ready=[c for c in job.clips if c['status']=='ready']
    if ready:
        temporary=job.destination/'shorts_prontos.zip.tmp'
        with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED,compresslevel=1) as pack:
            for clip in ready:
                check_cancelled()
                pack.write(job.destination/clip['name'],clip['name'])
                pack.write(job.destination/f'corte_{clip["number"]:02d}'/'legendas.srt',f'legendas/short_{clip["number"]:02d}.srt')
            pack.write(job.destination/'relatorio.json','relatorio.json')
        temporary.replace(job.destination/'shorts_prontos.zip')
        job.zip_name='shorts_prontos.zip'
    with job.lock:
        job.errors=[f'Corte {c["number"]}: {c.get("error", "falhou")}' for c in job.clips if c['status']=='failed']
        job.status='completed' if len(ready)==job.count else ('partial' if ready else 'failed')
        job.stage=job.status
        job.progress=100 if job.status=='completed' else round(100*len(ready)/max(1,job.count))
        job.message=f'{len(ready)} de {job.count} Shorts prontos.'
        job.persist()


def execute(job:Job,retry_number=None):
    token=cancel_event.set(job.cancel)
    job.destination.mkdir(parents=True,exist_ok=True)
    with job.lock:
        job.status='running'; job.persist()
    current=None
    try:
        check_cancelled(); require_dependencies()
        if retry_number is None:
            meta=metadata_youtube(job.url,lambda m:job.update(m,1,'analyzing'))
            (job.destination/'youtube-diagnostico.log').write_text(meta.get('_shortforge_diagnostics',''),encoding='utf-8')
            duration=float(meta.get('duration') or 0)
            if not math.isfinite(duration) or not 30<=duration<=12*3600:
                raise RuntimeError('Duração desconhecida, inferior a 30s ou superior a 12 horas.')
            job.title=str(meta.get('title') or 'Vídeo do YouTube')[:180]
            (job.destination/'origem.json').write_text(json.dumps({
                'titulo':job.title,'link':job.url,'duracao_segundos':duration,'id':meta.get('id')},ensure_ascii=False,indent=2),encoding='utf-8')
            heatmap=extract_heatmap(meta); energy=None
            if heatmap:
                job.selection_mode='Dados reais de Mais reproduzido do YouTube'
            else:
                job.selection_mode='Heurística local: energia, variação e pausas do áudio; não são dados de views nem análise semântica de cenas'
                job.update('Baixando áudio para seleção local...',5,'downloading')
                audio=download_audio(job.url,job.destination,lambda m:job.update(m,5,'downloading'))
                job.update('Analisando energia, variação e pausas...',10,'analyzing')
                energy=audio_energy(audio,duration,lambda m:job.update(m,10,'analyzing'))
                (job.destination/'energia.json').write_text(json.dumps(energy),encoding='utf-8')
            pool=pick_segments(duration,min(30,max(job.count*3,job.count+4)),job.length,heatmap=heatmap,energies=energy)
            pool=sorted(pool,key=lambda s:s.score,reverse=True)
            selected=sorted(pool[:job.count],key=lambda s:s.start)
            job.candidates=[dict(start=s.start,end=s.end,selection_reason=s.reason) for s in pool[job.count:]]
            if not selected: raise RuntimeError('Nenhum intervalo elegível.')
            with job.lock:
                job.clips=[dict(number=i,start=s.start,end=s.end,selection_reason=s.reason,status='queued')
                           for i,s in enumerate(selected,1)]
                if len(selected)<job.count:
                    job.message=f'Só há espaço para {len(selected)} cortes distintos; foram pedidos {job.count}.'
                job.persist()
            work=list(job.clips)
        else:
            work=[next(c for c in job.clips if c['number']==retry_number)]
            if (job.destination/'origem.json').exists():
                duration=float(json.loads((job.destination/'origem.json').read_text())['duracao_segundos'])
                if duration>180: job.candidates=[c for c in job.candidates if c['end']<=duration-30]
            # Older persisted jobs have no reserve candidates; derive them from
            # their own downloaded analysis audio, without fetching other sources.
            if not job.candidates and (job.destination/'origem.json').exists():
                audios=list(job.destination.glob('analise_audio.*'))
                audios=[a for a in audios if a.suffix in ('.webm','.m4a','.mp4','.opus')]
                if audios:
                    duration=float(json.loads((job.destination/'origem.json').read_text())['duracao_segundos'])
                    cache=job.destination/'energia.json'
                    if cache.exists(): energy=json.loads(cache.read_text())
                    else:
                        energy=audio_energy(audios[0],duration,lambda m:job.update(m,0,'analyzing'))
                        cache.write_text(json.dumps(energy),encoding='utf-8')
                    pool=pick_segments(duration,30,job.length,energies=energy)
                    occupied=[(c['start'],c['end']) for c in job.clips]
                    occupied.extend((r['start'],r['end']) for c in job.clips for r in c.get('rejected_candidates',[]))
                    job.candidates=[dict(start=s.start,end=s.end,selection_reason=s.reason)
                        for s in sorted(pool,key=lambda s:s.score,reverse=True)
                        if all(s.end<=a or s.start>=b for a,b in occupied)]
        whisper=None
        for entry in work:
            check_cancelled(); current=entry
            idx=entry['number']; folder=job.destination/f'corte_{idx:02d}'
            folder.mkdir(parents=True,exist_ok=True)
            base=15+int((idx-1)/max(1,job.count)*80)
            def notify(message,stage,offset=0):
                with job.lock: entry['status']=stage
                job.update(f'Corte {idx}: {message}',base+offset,stage)
            try:
                with job.lock:
                    entry.pop('error',None)
                    for derived in ('name','duration','width','height','audio','subtitles','subtitles_burned','face_box','facecam_detection','scene_analysis'):
                        entry.pop(derived,None)
                notify('Baixando trecho selecionado...','downloading')
                raw=download_section(job.url,entry['start'],entry['end'],folder,lambda m:notify(m,'downloading'))
                # Save an actual source preview even if detection subsequently fails.
                from .media import run
                preview=folder/'previa.jpg'
                run(['ffmpeg','-v','error','-nostdin','-y','-ss','2','-i',str(raw.resolve()),'-frames:v','1',str(preview.resolve())])
                notify('Procurando rosto persistente na composição...','detecting',2)
                box,description=identify_facecam(raw,job.facecam,job.manual_box)
                with job.lock:
                    entry.update(face_box=list(box),facecam_detection=description)
                notify('Verificando movimento e composição da cena...','analyzing',3)
                metrics=assess_scene(raw)
                with job.lock:
                    entry['scene_analysis']=metrics
                notify('Transcrevendo fala em português...','transcribing',4)
                if whisper is None: whisper=_load_whisper(job.model_name)
                subtitles=folder/'legendas.srt'
                n=make_srt(whisper,raw,subtitles,lambda m:notify(m,'transcribing',4))
                notify('Renderizando e validando vídeo, áudio e legendas...','rendering',6)
                out=job.destination/f'short_{idx:02d}.mp4'
                actual=render_split(raw,subtitles,out,box,job.resolution,lambda m:notify(m,'rendering',6))
                with job.lock:
                    entry.update(status='ready',name=out.name,duration=actual['duration'],width=actual['width'],
                        height=actual['height'],audio=actual['has_audio'],subtitles=n,subtitles_burned=True)
                    job.persist()
            except Cancelled:
                raise
            except UnsuitableScene as e:
                rejection=dict(start=entry['start'],end=entry['end'],reason=str(e))
                entry.setdefault('rejected_candidates',[]).append(rejection)
                if job.candidates:
                    replacement=job.candidates.pop(0)
                    archive=folder/f'descartado_{len(entry["rejected_candidates"]):02d}'
                    archive.mkdir(exist_ok=True)
                    for name in ('original.mp4','previa.jpg','legendas.srt'):
                        old=folder/name
                        if old.exists(): old.replace(archive/name)
                    with job.lock:
                        entry.update(replacement);entry.update(status='queued')
                        job.persist()
                    work.append(entry)
                    job.update(f'Corte {idx}: {e}',base,'analyzing')
                else:
                    entry.update(status='failed',error=f'{e} Não há mais candidatos distintos; não será entregue como pronto.')
                    job.persist()
            except Exception as e:
                with job.lock:
                    entry.update(status='failed',error=str(e)); job.persist()
        _finish(job)
    except Cancelled as e:
        with job.lock:
            for clip in job.clips:
                if clip['status']!='ready': clip.update(status='failed',error=str(e))
            job.status='cancelled'; job.stage='cancelled'; job.message=str(e); job.persist()
        # Ready files remain downloadable. No partial output is promoted to MP4.
    except Exception as e:
        with job.lock:
            job.status='failed'; job.stage='failed'; job.errors.append(str(e)); job.message=str(e); job.persist()
    finally:
        # Only disposable files created by this worker; source media is retained for retry.
        for temporary in [job.destination/'shorts_prontos.zip.tmp', *job.destination.glob('corte_*/legendas.srt.tmp')]:
            temporary.unlink(missing_ok=True)
        cancel_event.reset(token)
