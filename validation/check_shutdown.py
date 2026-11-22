"""Start the real entrypoint on a spare port and verify SIGTERM cleanup."""
import json,os,signal,socket,subprocess,sys,tempfile,time
from pathlib import Path
from urllib.request import urlopen
with socket.socket() as sock:
    sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
with tempfile.TemporaryDirectory() as tmp:
    code=f"import app;from pathlib import Path;app.PORT={port};app.OUT=Path({tmp!r});app.main()"
    process=subprocess.Popen([sys.executable,'-u','-c',code],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
                             env={**os.environ,'SHORTFORGE_NO_BROWSER':'1'},start_new_session=True)
    ready=False
    try:
        for _ in range(50):
            try:
                with urlopen(f'http://127.0.0.1:{port}/api/jobs/latest',timeout=.5) as r:assert r.status==200
                ready=True;break
            except OSError:time.sleep(.1)
        assert ready,'Servidor não respondeu'
        start=time.monotonic();process.send_signal(signal.SIGTERM)
        stdout,stderr=process.communicate(timeout=15)
        result=dict(port=port,http=200,exit_code=process.returncode,shutdown_seconds=time.monotonic()-start,stderr=stderr)
        Path('validation/encerramento.json').write_text(json.dumps(result,indent=2))
        print(result)
        assert process.returncode==0
    finally:
        if process.poll() is None:process.kill();process.wait()
