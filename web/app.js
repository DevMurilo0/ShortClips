'use strict';
const $=id=>document.getElementById(id);
let taskId=null, timer=null, polling=false;
let youtubeChannel=null, youtubeTimer=null;
const localMode=['127.0.0.1','localhost','::1'].includes(location.hostname);
const localAddress='http://127.0.0.1:8765';
function hasApi(){return localMode;}
function apiPath(path){if(!localMode)throw Error('Abra o ShortForge no seu computador.');return path;}
function authHeaders(){return {};}
function configureBackend(){
  $('backendPanel').hidden=localMode;
  $('submit').disabled=!localMode;
}
async function refreshYoutube(){
  if(!hasApi())return;
  try{
    const r=await fetch('/api/youtube/channel');const data=await r.json();
    if(!r.ok)throw Error('Canal indisponível');
    youtubeChannel=data.channel;
    $('youtubeChannel').textContent=youtubeChannel?'Canal: '+youtubeChannel.title:'Conta não conectada. Veja docs/YOUTUBE-UPLOAD.md.';
    $('youtubeAuto').disabled=!youtubeChannel;
    $('youtubeAuto').checked=false;
  }catch(e){youtubeChannel=null;$('youtubeAuto').disabled=true;$('youtubeAuto').checked=false;$('youtubeChannel').textContent='Não foi possível verificar o canal.';}
}
$('youtubeRefresh').addEventListener('click',refreshYoutube);
async function showYoutube(id){
  try{
    const r=await fetch('/api/youtube/jobs/'+encodeURIComponent(id));const data=await r.json();
    if(!r.ok||taskId!==id)return;
    $('youtubeUploads').textContent=data.uploads.length?data.uploads.map(u=>'Short '+u.number+': '+(u.video_id?'https://youtu.be/'+u.video_id:u.state==='paused'?'Pausado — '+u.error:u.state==='uploading'?'Enviando':'Na fila')).join(' | '):'Aguardando fila de publicação.';
  }catch(e){if(taskId===id)$('youtubeUploads').textContent='Não foi possível consultar uploads.';}
}
function asText(element, text) {element.textContent=String(text??'');}
function infoError(message) {$('jobErrors').textContent=message;}
function safePath(name) {return apiPath('/downloads/'+encodeURIComponent(taskId)+'/'+encodeURIComponent(name));}
function submissionError(message){
  infoError(message);$('output').classList.add('active');
  $('outputTitle').textContent='Não foi possível iniciar';
  $('statusTag').textContent='NÃO INICIADO';
  $('statusText').textContent='Corrija os dados e tente novamente.';
  $('submit').disabled=!hasApi();$('submit').textContent='Gerar Shorts ↗';
}

function render(job){
  if(!job)return;
  taskId=job.id;
  if(youtubeTimer){clearInterval(youtubeTimer);youtubeTimer=null;}
  if(job.youtube){showYoutube(job.id);youtubeTimer=setInterval(()=>showYoutube(job.id),5000);}
  else $('youtubeUploads').textContent='';
  $('output').classList.add('active');
  $('outputTitle').textContent=job.title||'Preparando vídeos';
  const labels={queued:'Aguardando',analyzing:'Analisando',downloading:'Baixando',transcribing:'Transcrevendo',detecting:'Detectando facecam',rendering:'Renderizando',ready:'Concluído',completed:'Concluído',partial:'Parcial',failed:'Falhou',cancelling:'Cancelando',cancelled:'Cancelado',expired:'Expirado',uploading:'Armazenando'};
  $('statusTag').textContent=labels[job.stage]||labels[job.status]||'Processando';
  $('statusText').textContent=job.message||'';
  $('progressFill').style.width=Math.min(100,job.progress||0)+'%';
  $('selection').textContent=job.selection_mode?('Seleção: '+job.selection_mode):'Buscando informações do vídeo...';
  $('submit').disabled=!hasApi()||['queued','running','cancelling'].includes(job.status);
  $('submit').textContent=$('submit').disabled?'Processando...':'Gerar Shorts ↗';
  const area=$('clipGrid');area.replaceChildren();
  for(const clip of job.clips||[]){

    const card=document.createElement('article');card.className='clip';
    const id=document.createElement('div');id.className='number';id.textContent='SHORT '+String(clip.number).padStart(2,'0');
    const title=document.createElement('h3');title.textContent='Corte '+clip.number+' · '+(labels[clip.status]||clip.status)+(clip.duration?' · '+Math.round(clip.duration)+' segundos':'');
    const detail=document.createElement('p');detail.textContent=clip.status==='ready'?clip.width+' × '+clip.height+' · '+clip.facecam_detection:(clip.error||'');
    if(clip.status!=='ready'){
      card.append(id,title,detail);
      if(clip.status==='failed' && localMode){
        const preview=document.createElement('a');preview.href=apiPath('/api/jobs/'+encodeURIComponent(taskId)+'/clips/'+clip.number+'/preview');preview.target='_blank';preview.textContent='Ver quadro original';card.append(preview);
        const retry=document.createElement('button');retry.type='button';retry.className='download';retry.textContent='Repetir este corte';retry.disabled=['queued','running','cancelling'].includes(job.status);
        retry.onclick=()=>retryClip(clip.number);card.append(retry);
      }
      area.appendChild(card);continue;
    }
    card.append(id,title,detail);
    const video=document.createElement('video');video.controls=true;video.playsInline=true;video.preload='metadata';video.src=safePath(clip.name);video.style.width='100%';card.append(video);
    const a=document.createElement('a');a.className='download';a.href=safePath(clip.name);a.download=clip.name;a.textContent='Baixar MP4 ↓';card.append(a);
    area.appendChild(card);
  }
  const zip=$('zipSlot');zip.replaceChildren();
  if(job.zip_name){
    const a=document.createElement('a');a.className='downloadBig';a.href=safePath(job.zip_name);a.download=job.zip_name;a.textContent='Baixar todos os Shorts (.ZIP) ↓';zip.append(a);
  }
  $('cancelJob').hidden=!['queued','running','cancelling'].includes(job.status);
  $('cancelJob').disabled=job.status==='cancelling';
  $('progressLabel').textContent=(job.clips||[]).filter(c=>c.status==='ready').length+' de '+job.count+' arquivos validados';
  infoError((job.errors||[]).join('\n'));
  if(['completed','partial','failed','cancelled','expired'].includes(job.status) && timer){clearInterval(timer);timer=null;}
}
async function poll(){
  if(!taskId||polling)return;
  polling=true;
  try{const r=await fetch(apiPath('/api/jobs/'+encodeURIComponent(taskId)),{headers:authHeaders(),signal:AbortSignal.timeout(10000)});{const data=await r.json();if(!r.ok)throw Error(data.error||'Falha ao consultar tarefa.');render(data)}}catch(e){infoError(e.message||'Não foi possível consultar o andamento. Tente novamente.')}
  finally{polling=false}
}
function startPolling(){if(timer)clearInterval(timer);timer=setInterval(poll,7000);poll()}
$('createForm').addEventListener('submit',async event=>{
  event.preventDefault();
  if(!hasApi()){submissionError('Abra '+localAddress+' depois de executar ./iniciar.sh.');return;}
  $('submit').disabled=true; $('submit').textContent='Preparando...'; infoError('');
  let selectedBox;
  try { selectedBox=manualBox(); } catch(e) { submissionError(e.message);return; }
  const payload={rights_confirmed:$('rightsConfirmed').checked,url:$('url').value.trim(),count:Number($('count').value),length:Number($('length').value),resolution:Number($('resolution').value),model:$('model').value,facecam:$('facecam').value,manual_box:selectedBox};
  if($('youtubeAuto').checked){
    if(!youtubeChannel||!$('youtubeKids').value){submissionError('Confirme o canal e se o conteúdo é destinado a crianças.');return;}
    const privacy=$('youtubePrivacy').value,interval=Number($('youtubeInterval').value);
    if(interval&&privacy!=='public'){submissionError('Agendamento exige visibilidade pública.');return;}
    if(!confirm('Enviar todos os Shorts deste lote ao canal '+youtubeChannel.title+' ('+privacy+ (interval?', agendado':'')+')?')){submissionError('Publicação não autorizada.');return;}
    payload.youtube={enabled:true,confirmed:true,channel:youtubeChannel.id,privacy,interval,made_for_kids:$('youtubeKids').value==='yes'};
  }
  try{
    const r=await fetch(apiPath('/api/jobs'),{method:'POST',headers:{'Content-Type':'application/json',...authHeaders()},body:JSON.stringify(payload)});
    const data=await r.json();
    if(!r.ok)throw new Error(data.error||'Não foi possível iniciar.');
    render(data.job);startPolling();$('output').scrollIntoView({block:'nearest',behavior:'smooth'});
  }catch(e){submissionError(e.message)}
});
configureBackend();
async function restoreLatest(){
  if(!hasApi())return;
  try{
    const r=await fetch(apiPath('/api/jobs/latest'),{headers:authHeaders(),signal:AbortSignal.timeout(10000)});
    const x=await r.json();
    if(r.ok&&x.job){render(x.job);if(['queued','running','cancelling'].includes(x.job.status))startPolling()}
  }catch(e){infoError('Não foi possível recuperar a última tarefa. Tente reconectar.');}
}
restoreLatest();

function manualBox(){
  const text=$('manualBox').value.trim();
  if(!text)return null;
  const box=text.split(/[,;\s]+/).map(Number);
  if(box.length!==4||box.some(v=>!Number.isFinite(v)))throw new Error('Região manual: use x y largura altura, em porcentagens.');
  return box;
}
async function retryClip(number){
  if(!hasApi())return;
  try{
    const box=manualBox();
    const payload={number};if(box)payload.manual_box=box;
    const r=await fetch(apiPath('/api/jobs/'+encodeURIComponent(taskId)+'/retry'),{method:'POST',headers:{'Content-Type':'application/json',...authHeaders()},body:JSON.stringify(payload)});
    const data=await r.json();if(!r.ok)throw new Error(data.error);render(data.job);startPolling();
  }catch(e){infoError(e.message)}
}
$('cancelJob').onclick=async()=>{
  if(!hasApi())return;
  try{
    const r=await fetch(apiPath('/api/jobs/'+encodeURIComponent(taskId)+'/cancel'),{method:'POST',headers:{'Content-Type':'application/json',...authHeaders()},body:'{}'});
    const data=await r.json();if(!r.ok)throw new Error(data.error);render(data.job);
  }catch(e){infoError(e.message)}
};
