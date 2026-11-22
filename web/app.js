'use strict';
const $=id=>document.getElementById(id);
let taskId=null, timer=null, polling=false;
function asText(element, text) {element.textContent=String(text??'');}
function infoError(message) {$('jobErrors').textContent=message;}
function safePath(name) {return '/downloads/'+encodeURIComponent(taskId)+'/'+encodeURIComponent(name);}
function render(job){
  if(!job)return;
  taskId=job.id;
  $('output').classList.add('active');
  $('outputTitle').textContent=job.title||'Preparando vídeos';
  const labels={queued:'Aguardando',analyzing:'Analisando',downloading:'Baixando',transcribing:'Transcrevendo',detecting:'Detectando facecam',rendering:'Renderizando',ready:'Concluído',completed:'Concluído',partial:'Parcial',failed:'Falhou',cancelling:'Cancelando',cancelled:'Cancelado'};
  $('statusTag').textContent=labels[job.stage]||labels[job.status]||'Processando';
  $('statusText').textContent=job.message||'';
  $('progressFill').style.width=Math.min(100,job.progress||0)+'%';
  $('selection').textContent=job.selection_mode?('Seleção: '+job.selection_mode):'Buscando informações do vídeo...';
  $('submit').disabled=['queued','running','cancelling'].includes(job.status);
  $('submit').textContent=$('submit').disabled?'Processando...':'Gerar Shorts ↗';
  const area=$('clipGrid');area.replaceChildren();
  for(const clip of job.clips||[]){

    const card=document.createElement('article');card.className='clip';
    const id=document.createElement('div');id.className='number';id.textContent='SHORT '+String(clip.number).padStart(2,'0');
    const title=document.createElement('h3');title.textContent='Corte '+clip.number+' · '+(labels[clip.status]||clip.status)+(clip.duration?' · '+Math.round(clip.duration)+' segundos':'');
    const detail=document.createElement('p');detail.textContent=clip.status==='ready'?clip.width+' × '+clip.height+' · '+clip.facecam_detection:(clip.error||'');
    if(clip.status!=='ready'){
      card.append(id,title,detail);
      if(clip.status==='failed'){
        const preview=document.createElement('a');preview.href='/api/jobs/'+encodeURIComponent(taskId)+'/clips/'+clip.number+'/preview';preview.target='_blank';preview.textContent='Ver quadro original';card.append(preview);
        const retry=document.createElement('button');retry.type='button';retry.className='download';retry.textContent='Repetir este corte';retry.disabled=['queued','running','cancelling'].includes(job.status);
        retry.onclick=()=>retryClip(clip.number);card.append(retry);
      }
      area.appendChild(card);continue;
    }
    const a=document.createElement('a');a.className='download';a.href=safePath(clip.name);a.download=clip.name;a.textContent='Baixar MP4 ↓';
    card.append(id,title,detail,a);area.appendChild(card);
  }
  const zip=$('zipSlot');zip.replaceChildren();
  if(job.zip_name){const a=document.createElement('a');a.className='downloadBig';a.href=safePath(job.zip_name);a.textContent='Baixar todos os Shorts (.ZIP) ↓';zip.appendChild(a)}
  $('cancelJob').hidden=!['queued','running','cancelling'].includes(job.status);
  $('cancelJob').disabled=job.status==='cancelling';
  $('progressLabel').textContent=(job.clips||[]).filter(c=>c.status==='ready').length+' de '+job.count+' arquivos validados';
  infoError((job.errors||[]).join('\n'));
  if(['completed','partial','failed','cancelled'].includes(job.status) && timer){clearInterval(timer);timer=null;}
}
async function poll(){
  if(!taskId||polling)return;
  polling=true;
  try{const r=await fetch('/api/jobs/'+encodeURIComponent(taskId),{signal:AbortSignal.timeout(10000)});if(r.ok)render(await r.json())}catch(e){infoError('Não foi possível consultar o andamento. O programa local ainda está aberto?')}
  finally{polling=false}
}
function startPolling(){if(timer)clearInterval(timer);timer=setInterval(poll,2500);poll()}
$('createForm').addEventListener('submit',async event=>{
  event.preventDefault();
  $('submit').disabled=true; $('submit').textContent='Preparando...'; infoError('');
  try { manualBox(); } catch(e) { infoError(e.message);$('output').classList.add('active');$('submit').disabled=false;return; }
  const payload={url:$('url').value.trim(),count:Number($('count').value),length:Number($('length').value),resolution:Number($('resolution').value),model:$('model').value,facecam:$('facecam').value,manual_box:manualBox()};
  try{
    const r=await fetch('/api/jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    const data=await r.json();
    if(!r.ok)throw new Error(data.error||'Não foi possível iniciar.');
    render(data.job);startPolling();$('output').scrollIntoView({block:'nearest',behavior:'smooth'});
  }catch(e){infoError(e.message);$('output').classList.add('active');$('submit').disabled=false;$('submit').textContent='Gerar Shorts ↗'}
});
(async()=>{try{const r=await fetch('/api/jobs/latest');const x=await r.json();if(x.job){render(x.job);if(['queued','running'].includes(x.job.status))startPolling()}}catch(e){/* servidor pode ainda estar iniciando */}})();

function manualBox(){
  const text=$('manualBox').value.trim();
  if(!text)return null;
  const box=text.split(/[,;\s]+/).map(Number);
  if(box.length!==4||box.some(v=>!Number.isFinite(v)))throw new Error('Região manual: use x y largura altura, em porcentagens.');
  return box;
}
async function retryClip(number){
  try{
    const box=manualBox();
    const payload={number};if(box)payload.manual_box=box;
    const r=await fetch('/api/jobs/'+encodeURIComponent(taskId)+'/retry',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    const data=await r.json();if(!r.ok)throw new Error(data.error);render(data.job);startPolling();
  }catch(e){infoError(e.message)}
}
$('cancelJob').onclick=async()=>{
  try{
    const r=await fetch('/api/jobs/'+encodeURIComponent(taskId)+'/cancel',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
    const data=await r.json();if(!r.ok)throw new Error(data.error);render(data.job);
  }catch(e){infoError(e.message)}
};
