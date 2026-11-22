from pathlib import Path
import json,sys,threading,time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from shortforge.pipeline import _load_whisper
from shortforge.media import make_srt
from shortforge.runtime import cancel_event,Cancelled
jid=Path('validation/real_1_id.txt').read_text().strip();source=Path('resultados')/jid/'corte_01/original.mp4'
model=_load_whisper('base');event=threading.Event();token=cancel_event.set(event)
timer=threading.Timer(1,event.set);start=time.monotonic();timer.start()
try:
    try:make_srt(model,source,Path('validation/cancelamento_transcricao.srt'),lambda m:None)
    except Cancelled:
        result={'real_model':'base','source':str(source),'cancel_requested_seconds':1,'cancel_observed_seconds':time.monotonic()-start,'cancelled':True}
        Path('validation/cancelamento_transcricao.json').write_text(json.dumps(result,indent=2));print(result)
    else:raise AssertionError('Transcrição não observou o cancelamento.')
finally:
    timer.join();cancel_event.reset(token)
