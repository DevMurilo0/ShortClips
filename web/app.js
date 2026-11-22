'use strict';
const $=id=>document.getElementById(id);
let taskId=null, timer=null, polling=false;
const localMode=['127.0.0.1','localhost','::1'].includes(location.hostname);
let apiBase=(window.SHORTFORGE_API_URL||localStorage.getItem('shortforge_api_url')||'').replace(/\/$/,'');
let apiKey=sessionStorage.getItem('shortforge_public_access_key')||'';
let connected=localMode;
function authHeaders(){return !localMode&&apiKey?{'Authorization':'Bearer '+apiKey}:{};}
function apiPath(path){return apiBase+path;}
function hasApi(){return connected;}
function apiNotice(message){const el=$('backendStatus');if(el)el.textContent=message;}
function enforceCloudLimits(){
  if(localMode)return;
  for(const [id,value] of [['count','5'],['length','45'],['resolution','720'],['model','base']]){
    const el=$(id);if(el){el.value=value;el.disabled=true;}
  }
}
async function refreshUsage(){
  if(!hasApi()||localMode)return;
  const panel=$('usagePanel');if(!panel)return;
  try{
    const response=await fetch(apiPath('/api/usage'),{
      headers:authHeaders(), signal:AbortSignal.timeout(12000)
    });
    if(!response.ok)throw Error('Sem dados de consumo.');
    const usage=await response.json();
    panel.hidden=false;
    $('usageJobs').textContent=usage.jobs_month+' de '+usage.jobs_month_limit+' processamentos neste mês';
    const m=usage.usage || {};
    $('usageEstimate').textContent='CPU '+(m.cpu_monthly_percent??'—')+
      '% · Memória '+(m.memory_monthly_percent??'—')+
      '% · Blob (estoque vs. 1 GB) '+(m.storage_vs_1gb_percent??'—')+
      '% · Transferência estimada '+(m.sandbox_transfer_monthly_percent??'—')+
      '%. Valores do processamento, não a fatura da Vercel.';
  }catch(e){panel.hidden=true;}
}
async function signedDownload(pathname){
  const url=new URL(apiPath('/api/download'),location.href);
  url.searchParams.set('pathname',pathname);
  const response=await fetch(url,{headers:authHeaders(),signal:AbortSignal.timeout(15000)});
  const data=await response.json();
  if(!response.ok||!data.url)throw Error(data.error||'Não foi possível assinar o download.');
  // A URL privada vale poucos minutos; o token nunca entra na query.
  window.location.assign(data.url);
}
async function configureBackend(){
  const panel=$('backendPanel');
  if(!panel)return;
  panel.hidden=localMode;
  if(localMode)return;
  enforceCloudLimits();
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
      apiBase=url.origin;apiKey=submittedKey;connected=true;
      localStorage.setItem('shortforge_api_url',apiBase);
      sessionStorage.setItem('shortforge_public_access_key',apiKey);
      $('submit').disabled=false;apiNotice('Servidor verificado. Acesso configurado nesta aba.');
      await refreshUsage();
    }catch(e){apiNotice('Conexão não estabelecida: '+(e.message||e));}
  });
}

function asText(element, text) {element.textContent=String(text??'');}
function infoError(message) {$('jobErrors').textContent=message;}
function safePath(name) {return apiPath('/downloads/'+encodeURIComponent(taskId)+'/'+encodeURIComponent(name));}
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
      if(clip.status==='failed'){
        if(localMode){
          const preview=document.createElement('a');preview.href=apiPath('/api/jobs/'+encodeURIComponent(taskId)+'/clips/'+clip.number+'/preview');preview.target='_blank';preview.textContent='Ver quadro original';card.append(preview);
        }
        const retry=document.createElement('button');retry.type='button';retry.className='download';retry.textContent='Repetir este corte';retry.disabled=['queued','running','cancelling'].includes(job.status);
        retry.onclick=()=>retryClip(clip.number);if(localMode)card.append(retry);
      }
      area.appendChild(card);continue;
    }
    const a=document.createElement('a');a.className='download';
    const publicUrl=(!localMode && clip.download_url)||null;
    if(!localMode && clip.blob_path){
      a.href='#';a.textContent='Baixar MP4 seguro ↓';
      a.onclick=async event=>{
        event.preventDefault();
        try{await signedDownload(clip.blob_path);}catch(e){infoError(e.message);}
      };
      card.append(id,title,detail,a);
    }else if(!localMode&&!publicUrl){
      const note=document.createElement('p');note.textContent='Armazenamento de vídeo indisponível para este corte.';
      card.append(id,title,detail,note);
    }else{
      a.href=publicUrl||safePath(clip.name);a.download=clip.name;a.textContent='Baixar MP4 ↓';
      card.append(id,title,detail,a);
    }
    area.appendChild(card);
  }
  const zip=$('zipSlot');zip.replaceChildren();
  if(job.zip_name && (localMode||job.zip_url||job.zip_path)){
    const a=document.createElement('a');a.className='downloadBig';
    a.href=(!localMode&&job.zip_url)|| (localMode?safePath(job.zip_name):'#');
    a.textContent='Baixar todos os Shorts (.ZIP) ↓';
    if(!localMode && job.zip_path){
      a.onclick=async event=>{
        event.preventDefault();
        try{await signedDownload(job.zip_path);}catch(e){infoError(e.message);}
      };
    }
    zip.appendChild(a);
  }
  $('cancelJob').hidden=!['queued','running','cancelling'].includes(job.status);
  $('cancelJob').disabled=job.status==='cancelling';
  $('progressLabel').textContent=(job.clips||[]).filter(c=>c.status==='ready').length+' de '+job.count+' arquivos validados';
  infoError((job.errors||[]).join('\n'));
  if(['completed','partial','failed','cancelled'].includes(job.status) && timer){clearInterval(timer);timer=null;refreshUsage();}
}
async function poll(){
  if(!taskId||polling)return;
  polling=true;
  try{const r=await fetch(apiPath('/api/jobs/'+encodeURIComponent(taskId)),{headers:authHeaders(),signal:AbortSignal.timeout(10000)});if(r.ok)render(await r.json())}catch(e){infoError('Não foi possível consultar o andamento. O programa local ainda está aberto?')}
  finally{polling=false}
}
function startPolling(){if(timer)clearInterval(timer);timer=setInterval(poll,2500);poll()}
$('createForm').addEventListener('submit',async event=>{
  event.preventDefault();
  if(!hasApi()){infoError('É necessário conectar um backend de processamento antes de gerar Shorts.');return;}
  $('submit').disabled=true; $('submit').textContent='Preparando...'; infoError('');
  try { manualBox(); } catch(e) { infoError(e.message);$('output').classList.add('active');$('submit').disabled=false;return; }
  const payload={url:$('url').value.trim(),count:Number($('count').value),length:Number($('length').value),resolution:Number($('resolution').value),model:$('model').value,facecam:$('facecam').value,manual_box:manualBox()};
  try{
    const r=await fetch(apiPath('/api/jobs'),{method:'POST',headers:{'Content-Type':'application/json',...authHeaders()},body:JSON.stringify(payload)});
    const data=await r.json();
    if(!r.ok)throw new Error(data.error||'Não foi possível iniciar.');
    render(data.job);startPolling();$('output').scrollIntoView({block:'nearest',behavior:'smooth'});
  }catch(e){infoError(e.message);$('output').classList.add('active');$('submit').disabled=false;$('submit').textContent='Gerar Shorts ↗'}
});
configureBackend();
(async()=>{if(!hasApi())return;try{const r=await fetch(apiPath('/api/jobs/latest'),{headers:authHeaders()});const x=await r.json();if(x.job){render(x.job);if(['queued','running'].includes(x.job.status))startPolling()}}catch(e){/* servidor pode ainda estar iniciando */}})();

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
