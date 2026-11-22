"""Exercise the running server with the mandatory public YouTube URL. No mocks."""
import json
from pathlib import Path
import sys
import time
from urllib.request import Request,urlopen

base='http://127.0.0.1:8765'
count=int(sys.argv[1])
with urlopen(Request(base+'/api/jobs',data=json.dumps(dict(url='https://youtu.be/yWvnOWILFk0?si=XVqvHx0fr3Y-jR2_',count=count,length=45,resolution=720,model='base')).encode(),headers={'Content-Type':'application/json'})) as r:
    initial=json.load(r)
jid=initial['job']['id'];Path(f'validation/real_{count}_id.txt').write_text(jid)
print('JOB',jid,flush=True)
previous=''
while True:
    with urlopen(base+'/api/jobs/'+jid,timeout=15) as r:job=json.load(r)
    message=job['status']+' '+job['message']
    if message!=previous:print(message,flush=True);previous=message
    if job['status'] not in ('queued','running','cancelling'):break
    time.sleep(3)
Path(f'validation/real_{count}_resultado.json').write_text(json.dumps(job,ensure_ascii=False,indent=2))
if job['status']!='completed':sys.exit(1)
with urlopen(base+'/downloads/'+jid+'/'+job['zip_name'],timeout=60) as r:
    zip_bytes=r.read()
Path(f'validation/real_{count}_download.zip').write_bytes(zip_bytes)
print('ZIP baixado via HTTP:',len(zip_bytes),'bytes',flush=True)
