"""Real cached-video transcription in an isolated server; interrupt while native ASR runs."""
import json,os,signal,socket,subprocess,sys,tempfile,time,shutil
from pathlib import Path
from urllib.request import Request,urlopen
root=Path.cwd();jid=Path('validation/real_1_id.txt').read_text().strip();source=(root/'resultados'/jid/'corte_01/original.mp4').resolve()
with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
with tempfile.TemporaryDirectory(prefix='shortforge-shutdown-') as tmp:
    out=Path(tmp);work=out/'abc/corte_01';work.mkdir(parents=True);shutil.copyfile(source,work/'original.mp4')
    code=f'''import app
from pathlib import Path
from shortforge.pipeline import Job
app.PORT={port};app.OUT=Path({tmp!r})
j=Job('abc','https://youtu.be/yWvnOWILFk0',1,45,720,'auto','base',app.OUT/'abc',status='failed',candidates=[dict(start=6409,end=6454,selection_reason='reserva')])
j.clips=[dict(number=1,start=4782,end=4827,status='failed')];j.persist()
app.main()
'''
    proc=subprocess.Popen([sys.executable,'-u','-c',code],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True,env={**os.environ,'SHORTFORGE_NO_BROWSER':'1'})
    base=f'http://127.0.0.1:{port}'
    try:
        for _ in range(100):
            try:
                with urlopen(base+'/api/jobs/abc',timeout=.5) as r:json.load(r)
                break
            except OSError:time.sleep(.1)
        with urlopen(Request(base+'/api/jobs/abc/retry',data=b'{"number":1}',headers={'Content-Type':'application/json'})) as r:assert r.status==202
        for _ in range(240):
            with urlopen(base+'/api/jobs/abc',timeout=5) as r:state=json.load(r)
            if 'tempos por palavra' in state['message']:break
            if state['status'] in ('failed','completed'):raise RuntimeError(state)
            time.sleep(.25)
        else:raise RuntimeError('Transcrição não iniciou')
        time.sleep(1);start=time.monotonic();proc.send_signal(signal.SIGTERM)
        stdout,stderr=proc.communicate(timeout=55)
        state=json.loads((out/'abc/tarefa.json').read_text())
        result=dict(exit_code=proc.returncode,elapsed=time.monotonic()-start,status=state['status'],
            stage=state['stage'],temporary_renders=[str(p) for p in work.glob('render_*')],stdout=stdout,stderr=stderr)
        Path('validation/encerramento_ativo.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(result)
        assert proc.returncode==0,result
        assert state['status']=='cancelled',result
    finally:
        if proc.poll() is None:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
