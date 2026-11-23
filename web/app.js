'use strict';
const $=id=>document.getElementById(id);
let taskId=null, timer=null, polling=false;
const localMode=['127.0.0.1','localhost','::1'].includes(location.hostname);
let apiBase=(localMode?'':(window.SHORTFORGE_API_URL||localStorage.getItem('shortforge_api_url')||'')).replace(/\/$/,'');
let apiKey=sessionStorage.getItem('shortforge_public_access_key')||'';
let connected=localMode;
function authHeaders(){return !localMode&&apiKey?{'Authorization':'Bearer '+apiKey}:{};}
function apiPath(path){return apiBase+path;}
function hasApi(){return connected;}
function apiNotice(message){const el=$('backendStatus');if(el)el.textContent=message;}
async function configureBackend(){
  const panel=$('backendPanel');
  if(!panel)return;
  panel.hidden=localMode;
  if(localMode)return;
  $('backendURL').value=apiBase;
  $('backendAccessKey').value=apiKey;
  $('submit').disabled=!hasApi();
  apiNotice('Verifique a conexão e informe a chave de acesso antes de gerar vídeos.');
  $('saveBackend').addEventListener('click',async()=>{
    const value=$('backendURL').value.trim().replace(/\/$/,'');
    const submittedKey=$('backendAccessKey').value.trim();
    if(!submittedKey){apiNotice('Informe a chave de acesso.');return;}
    let url;
    try{
      url=new URL(value);
      if(url.protocol!=='https:'&&!['localhost','127.0.0.1'].includes(url.hostname))throw Error('O servidor público precisa de HTTPS.');
      if(url.pathname!=='/'||url.search||url.hash)throw Error('Informe só o domínio da API, sem caminho.');
      apiNotice('Verificando a API...');
      const r=await fetch(url.origin+'/api/health',{signal:AbortSignal.timeout(8000)});
      const check=await r.json();
      if(!r.ok||check.ok!==true)throw Error('Esta URL não respondeu como API ShortForge.');
      if(check.ready===false)throw Error('O servidor existe, mas seu worker de vídeos ainda não está configurado.');
      const access=await fetch(url.origin+(check.mode==='sandbox'?'/api/usage':'/api/jobs/latest'),{headers:{Authorization:'Bearer '+submittedKey},signal:AbortSignal.timeout(8000)});
      if(!access.ok&&access.status!==404)throw Error('Chave de acesso inválida ou API indisponível.');
      apiBase=url.origin;apiKey=submittedKey;connected=true;
      localStorage.setItem('shortforge_api_url',apiBase);
      sessionStorage.setItem('shortforge_public_access_key',apiKey);
      $('submit').disabled=false;apiNotice('Servidor verificado. Acesso configurado nesta aba.');
      await restoreLatest();
    }catch(e){apiNotice('Conexão não estabelecida: '+(e.message||e));}
  });
}

function asText(element, text) {element.textContent=String(text??'');}
function infoError(message) {$('jobErrors').textContent=message;}
function safePath(name) {return apiPath('/downloads/'+encodeURIComponent(taskId)+'/'+encodeURIComponent(name));}
function remoteDownloadLink(endpoint, name, label, className='download') {
  const button=document.createElement('button');button.type='button';button.className=className;button.textContent=label;
  button.onclick=async()=>{
    button.disabled=true;
    try{
      if(!endpoint.startsWith('/api/download?'))throw Error('Endereço de download inválido.');
      const response=await fetch(apiPath(endpoint),{headers:authHeaders(),signal:AbortSignal.timeout(15000)});
      const data=await response.json();
      if(!response.ok)throw Error(data.error||'Falha ao autorizar o download.');
      const link=document.createElement('a');link.href=data.url;link.download=name;link.rel='noopener';
      document.body.append(link);link.click();link.remove();
    }catch(error){infoError(error.message)}finally{button.disabled=false}
  };
  return button;
}
function render(job){
  if(!job)return;
  taskId=job.id;
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
    if(!localMode && clip.download_endpoint){
      card.append(remoteDownloadLink(clip.download_endpoint,clip.name,'Baixar MP4 ↓'));
      const preview=remoteDownloadLink(clip.download_endpoint,clip.name,'Assistir Short');
      // Playback uses a fresh, short-lived private URL; no credential in the URL.
      preview.onclick=async()=>{
        preview.disabled=true;
        try{
          const response=await fetch(apiPath(clip.download_endpoint),{headers:authHeaders(),signal:AbortSignal.timeout(15000)});
          const data=await response.json();if(!response.ok)throw Error(data.error);
          const video=document.createElement('video');video.controls=true;video.playsInline=true;video.preload='metadata';video.src=data.url;video.style.width='100%';
          preview.replaceWith(video);
        }catch(e){infoError(e.message);preview.disabled=false}
      };card.append(preview);
    }else if(localMode || clip.download_url){
      if(localMode){
        const video=document.createElement('video');video.controls=true;video.playsInline=true;video.preload='metadata';video.src=safePath(clip.name);video.style.width='100%';card.append(video);
      }
      const a=document.createElement('a');a.className='download';a.href=localMode?safePath(clip.name):clip.download_url;a.download=clip.name;a.textContent='Baixar MP4 ↓';card.append(a);
    }
    area.appendChild(card);
  }
  const zip=$('zipSlot');zip.replaceChildren();
  if(job.zip_name && !localMode && job.zip_download_endpoint){
    zip.append(remoteDownloadLink(job.zip_download_endpoint,job.zip_name,'Baixar todos os Shorts (.ZIP) ↓','downloadBig'));
  }else if(job.zip_name && (localMode || job.zip_url)){
    const a=document.createElement('a');a.className='downloadBig';a.href=localMode?safePath(job.zip_name):job.zip_url;a.textContent='Baixar todos os Shorts (.ZIP) ↓';zip.append(a);
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
  if(!hasApi()){infoError('É necessário conectar um backend de processamento antes de gerar Shorts.');return;}
  $('submit').disabled=true; $('submit').textContent='Preparando...'; infoError('');
  try { manualBox(); } catch(e) { infoError(e.message);$('output').classList.add('active');$('submit').disabled=false;return; }
  const payload={rights_confirmed:$('rightsConfirmed').checked,url:$('url').value.trim(),count:Number($('count').value),length:Number($('length').value),resolution:Number($('resolution').value),model:$('model').value,facecam:$('facecam').value,manual_box:manualBox()};
  try{
    const r=await fetch(apiPath('/api/jobs'),{method:'POST',headers:{'Content-Type':'application/json',...authHeaders()},body:JSON.stringify(payload)});
    const data=await r.json();
    if(!r.ok)throw new Error(data.error||'Não foi possível iniciar.');
    render(data.job);startPolling();$('output').scrollIntoView({block:'nearest',behavior:'smooth'});
  }catch(e){infoError(e.message);$('output').classList.add('active');$('submit').disabled=false;$('submit').textContent='Gerar Shorts ↗'}
});
if(localMode && window.SHORTFORGE_LOCAL_CONTROLLED){
  document.querySelector('#createForm').previousElementSibling.textContent='Teste local: use um vídeo autorizado com fala, de 30 a 120 segundos. Comece com um Short de 30 segundos em 720p.';
  for(const [id,allowed] of Object.entries({count:['1','3','5'],length:['30','35','45'],resolution:['720']})){
    for(const option of [...$(id).options])if(!allowed.includes(option.value))option.remove();
  }
}
configureBackend();
async function restoreLatest(){
  if(!hasApi())return;
  try{
    const r=await fetch(apiPath('/api/jobs/latest'),{headers:authHeaders(),signal:AbortSignal.timeout(10000)});
    const x=await r.json();
    if(r.ok&&x.job){render(x.job);if(['queued','running'].includes(x.job.status))startPolling()}
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
  try{
    const box=manualBox();
    const payload={number};if(box)payload.manual_box=box;
    const r=await fetch(apiPath('/api/jobs/'+encodeURIComponent(taskId)+'/retry'),{method:'POST',headers:{'Content-Type':'application/json',...authHeaders()},body:JSON.stringify(payload)});
    const data=await r.json();if(!r.ok)throw new Error(data.error);render(data.job);startPolling();
  }catch(e){infoError(e.message)}
}
$('cancelJob').onclick=async()=>{
  try{
    const r=await fetch(apiPath('/api/jobs/'+encodeURIComponent(taskId)+'/cancel'),{method:'POST',headers:{'Content-Type':'application/json',...authHeaders()},body:'{}'});
    const data=await r.json();if(!r.ok)throw new Error(data.error);render(data.job);
  }catch(e){infoError(e.message)}
};
