from pathlib import Path
import json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from shortforge.media import render_split
jid=Path('validation/real_1_id.txt').read_text().strip();root=Path('resultados')/jid
job=json.loads((root/'tarefa.json').read_text());clip=job['clips'][0]
output=Path('validation/short_real_1080.mp4')
result=render_split(root/'corte_01/original.mp4',root/'corte_01/legendas.srt',output,clip['face_box'],1080,print)
Path('validation/resolucao_1080.json').write_text(json.dumps(result,indent=2))
print(result)
