"""Independent artifact inspection; writes ffprobe, decode, frame and burn-in evidence."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import zipfile
import cv2
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from shortforge.media import validate_output, validate_srt, build_filters

count=int(sys.argv[1]);root=Path(__file__).resolve().parents[1]
jid=(root/f'validation/real_{count}_id.txt').read_text().strip()
folder=root/'resultados'/jid
job=json.loads((folder/'tarefa.json').read_text())
evidence=root/'validation'/f'evidencias_{jid}';evidence.mkdir(exist_ok=True)
report=[]
for clip in job['clips']:
    if clip['status']!='ready':raise RuntimeError(clip)
    path=folder/clip['name'];work=folder/f'corte_{clip["number"]:02d}'
    probe=subprocess.run(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(path)],capture_output=True,text=True,check=True)
    (evidence/(path.stem+'_ffprobe.json')).write_text(probe.stdout)
    data=validate_output(path,720,decode=True)
    # Compare actual decoded original/output waveforms at identical timestamps.
    waves=[]
    for audio_path in (work/'original.mp4',path):
        raw=subprocess.run(['ffmpeg','-v','error','-nostdin','-i',str(audio_path),'-vn','-ac','1','-ar','8000','-f','f32le','-'],capture_output=True,check=True).stdout
        waves.append(np.frombuffer(raw,dtype='<f4'))
    n=min(map(len,waves));left=waves[0][:n];right=waves[1][:n]
    correlation=float(np.corrcoef(left,right)[0,1])
    if not np.isfinite(correlation) or correlation<.90:raise RuntimeError(f'Áudio alterado/deslocado: correlação {correlation}')
    captions=validate_srt(work/'legendas.srt',data['duration'])
    cap=cv2.VideoCapture(str(path));frames=[]
    for label,t in [('inicio',.5),('meio',data['duration']/2),('fim',data['duration']-.5)]:
        cap.set(cv2.CAP_PROP_POS_MSEC,t*1000);ok,frame=cap.read()
        if not ok:raise RuntimeError('Frame não decodificável')
        cv2.imwrite(str(evidence/f'{path.stem}_{label}.png'),frame)
        scaled=cv2.resize(frame,(360,640));cv2.putText(scaled,f'{label} {t:.2f}s',(8,25),cv2.FONT_HERSHEY_SIMPLEX,.6,(0,255,255),2)
        frames.append(scaled)
    cv2.imwrite(str(evidence/f'{path.stem}_contato.jpg'),np.hstack(frames))
    # Compare an actual captioned frame against the same composition without captions.
    a,b,text=next(c for c in captions if c[1]-c[0]>.3)
    t=(a+b)/2
    cap.set(cv2.CAP_PROP_POS_MSEC,t*1000);ok,actual=cap.read();cap.release()
    if not ok:raise RuntimeError('Não foi possível extrair quadro legendado')
    cv2.imwrite(str(evidence/f'{path.stem}_legenda.png'),actual)
    filters=build_filters(clip['face_box'],720).split('[stack]subtitles=')[0]+'[stack]format=yuv420p[v]'
    reference=evidence/f'{path.stem}_referencia_sem_legenda.png'
    subprocess.run(['ffmpeg','-v','error','-nostdin','-y','-filter_complex_threads','2','-ss',str(t),
        '-i',str(work/'original.mp4'),'-filter_complex',filters,'-map','[v]','-frames:v','1',str(reference)],check=True)
    baseline=cv2.imread(str(reference))
    region=actual[1000:];base=baseline[1000:]
    white=np.all(region>205,axis=2)
    introduced=white & (np.max(np.abs(region.astype(np.int16)-base.astype(np.int16)),axis=2)>80)
    glyph_pixels=int(introduced.sum())
    if glyph_pixels<100:raise RuntimeError(f'Incorporação não comprovada: só {glyph_pixels} pixels novos')
    report.append(dict(name=path.name,path=str(path),duration=data['duration'],width=data['width'],height=data['height'],
        audio=data['has_audio'],original_audio_correlation=correlation,decode='passed',captions=len(captions),caption_time=t,caption_text=text,
        introduced_caption_pixels=glyph_pixels,facecam=clip['facecam_detection'],face_box=clip['face_box'],
        start=clip['start'],end=clip['end'],sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
with zipfile.ZipFile(folder/job['zip_name']) as pack:
    assert pack.testzip() is None
    expected={'relatorio.json'}|{c['name'] for c in job['clips']}|{f'legendas/short_{c["number"]:02d}.srt' for c in job['clips']}
    assert set(pack.namelist())==expected
    for clip in job['clips']:assert pack.read(clip['name'])==(folder/clip['name']).read_bytes()
assert (root/f'validation/real_{count}_download.zip').read_bytes()==(folder/job['zip_name']).read_bytes()
ordered=sorted(report,key=lambda c:c['start'])
for a,b in zip(ordered,ordered[1:]):assert a['end']<=b['start']
(evidence/'validacao.json').write_text(json.dumps(dict(job=jid,clips=report,zip='CRC, contents, MP4 bytes and HTTP download passed'),ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False,indent=2))
