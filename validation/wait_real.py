import json
from pathlib import Path
import sys,time
from urllib.request import urlopen
count=int(sys.argv[1]);base='http://127.0.0.1:8765';jid=Path(f'validation/real_{count}_id.txt').read_text().strip()
previous=''
while True:
 with urlopen(base+'/api/jobs/'+jid,timeout=15) as r:job=json.load(r)
 message=job['status']+' '+job['message']
 if message!=previous:print(message,flush=True);previous=message
 if job['status'] not in ('queued','running','cancelling'):break
 time.sleep(3)
Path(f'validation/real_{count}_resultado.json').write_text(json.dumps(job,ensure_ascii=False,indent=2))
if job['status']!='completed':sys.exit(1)
with urlopen(base+'/downloads/'+jid+'/'+job['zip_name'],timeout=60) as r:raw=r.read()
Path(f'validation/real_{count}_download.zip').write_bytes(raw)
print('ZIP baixado via HTTP:',len(raw),'bytes',flush=True)
