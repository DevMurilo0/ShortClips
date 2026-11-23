'use strict';

const ROUTE = /^\/api\/(?:health|usage|jobs(?:\/latest|\/[a-f0-9]{32}(?:\/(?:cancel|retry))?)?|download(?:\?pathname=[^#]+)?)$/;

function createHandler(upstreamFetch = fetch) {
  return async function handler(req, res) {
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('X-Content-Type-Options', 'nosniff');
    const env = process.env;
    const preview = env.VERCEL_ENV === 'preview';
    const production = env.VERCEL_ENV === 'production' &&
      env.SHORTFORGE_OWNER_PRODUCTION_ENABLED === '1';
    if (!preview && !production) {
      return res.status(503).json({error:'Acesso privado do proprietário não habilitado neste ambiente.'});
    }
    // Production only after Vercel Authentication protects All Deployments.
    // This opt-in is NOT a substitute for Vercel Authentication.
    const deploymentHost = String(req.headers.host || env.VERCEL_URL || '').toLowerCase();
    const validFrontend = /^short-clips-[a-z0-9]+-murilo15\.vercel\.app$/.test(deploymentHost) ||
      (production && deploymentHost === 'short-clips-tan.vercel.app');
    if (!validFrontend) {
      return res.status(503).json({error:'Domínio do ShortForge não autorizado.'});
    }
    const expectedOrigin = 'https://' + deploymentHost;
    const origin = req.headers.origin;
    if ((origin && origin !== expectedOrigin) || req.headers['sec-fetch-site'] === 'cross-site' ||
        (req.headers.host && req.headers.host !== deploymentHost)) {
      return res.status(403).json({error:'Origem não permitida.'});
    }
    if (!['GET', 'POST'].includes(req.method)) {
      return res.status(405).json({error:'Método não permitido.'});
    }
    const path = req.query.path;
    if (typeof path !== 'string' || path.length > 2048 || !ROUTE.test(path)) {
      return res.status(400).json({error:'Rota de API inválida.'});
    }
    const createJob = req.method === 'POST' && path === '/api/jobs';
    const cancelJob = req.method === 'POST' && /^\/api\/jobs\/[a-f0-9]{32}\/cancel$/.test(path);
    if (req.method === 'POST' && !createJob && !cancelJob) {
      return res.status(405).json({error:'Método não permitido nesta rota.'});
    }
    // A admissão exige opt-in privado independente de conectar/consultar a API.
    // O backend ainda impõe uma única tarefa, fonte autorizada e VM de 10 minutos.
    const admissionReady = preview ? env.SHORTFORGE_PREVIEW_ADMISSION === '1' :
      env.SHORTFORGE_PRODUCTION_ADMISSION === '1';
    if (createJob && !admissionReady) {
      return res.status(503).json({error:'Geração pausada até confirmar a franquia e o processamento real.'});
    }
    let body;
    if (req.method === 'POST') {
      if (origin !== expectedOrigin) {
        return res.status(403).json({error:'A geração exige acesso pelo ShortForge autenticado.'});
      }
      if (String(req.headers['content-type'] || '').split(';')[0].trim().toLowerCase() !== 'application/json' ||
          !req.body || typeof req.body !== 'object' || Array.isArray(req.body)) {
        return res.status(400).json({error:'Envie um objeto JSON válido.'});
      }
      body = JSON.stringify(req.body);
      if (Buffer.byteLength(body) > 4096) {
        return res.status(413).json({error:'Pedido excede o limite de tamanho.'});
      }
      if (createJob) {
        const j = req.body;
        const box = j.manual_box;
        const validBox = box == null || (Array.isArray(box) && box.length === 4 &&
          box.every(v=>typeof v === 'number' && Number.isFinite(v)) &&
          box[0]>=0 && box[1]>=0 && box[2]>0 && box[3]>0 &&
          box[0]+box[2]<=100 && box[1]+box[3]<=100);
        const validPreviewBox = !preview || Array.isArray(box);
        const validBudget = preview ? (j.count===1 && j.length===30) :
          (Number.isInteger(j.count) && j.count>=1 && j.count<=5 &&
           Number.isInteger(j.length) && j.length>=30 && j.length<=45);
        if (j.rights_confirmed !== true || !validBudget || j.resolution !== 720 ||
            typeof j.url !== 'string' || j.url.length > 2048 ||
            !validBox || !validPreviewBox) {
          return res.status(400).json({error:'Pedido fora dos limites de processamento autorizado (720p, até 5 Shorts de 30–45s).'});
        }
      }
    }
    let base;
    try {
      base = new URL(env.SHORTFORGE_PUBLIC_API_URL);
      if (base.protocol !== 'https:' || base.username || base.password || base.port ||
          base.pathname !== '/' || base.search || base.hash ||
          !(preview ? /^backend-short-clips-[a-z0-9]+-murilo15\.vercel\.app$/.test(base.hostname) :
            base.hostname === 'backend-short-clips.vercel.app')) throw Error();
    } catch {
      return res.status(503).json({error:'Backend privado não configurado para este ambiente.'});
    }
    const key = preview ? env.SHORTFORGE_PREVIEW_ACCESS_KEY : env.SHORTFORGE_OWNER_ACCESS_KEY;
    const share = preview ? env.SHORTFORGE_BACKEND_PREVIEW_SHARE : '';
    const bypass = env.SHORTFORGE_BACKEND_PROTECTION_BYPASS || '';
    if (!key || key.length < 32 || key.includes('[SENSITIVE]') ||
        (!share && !bypass) || share.includes('[SENSITIVE]') || bypass.includes('[SENSITIVE]')) {
      return res.status(503).json({error:'Credenciais privadas entre site e backend não configuradas.'});
    }
    const resource = new URL(path, base);
    const target = new URL(resource);
    // All bypass/share credentials remain exclusively in the serverless function.
    if (share) target.searchParams.set('_vercel_share', share);
    try {
      const headers = {Accept:'application/json',Authorization:'Bearer ' + key};
      if (bypass) headers['x-vercel-protection-bypass'] = bypass;
      if (req.method === 'POST') headers['Content-Type'] = 'application/json';
      let response = await upstreamFetch(target, {
        method:req.method, redirect:'manual', signal:AbortSignal.timeout(15000),
        headers, ...(body ? {body} : {})
      });
      if (response.status >= 300 && response.status < 400) {
        const location = new URL(response.headers.get('location') || '', target);
        if (location.href !== resource.href) throw Error();
        const cookie = response.headers.getSetCookie()
          .map(value => value.split(';', 1)[0])
          .find(value => value.startsWith('_vercel_jwt='));
        if (!cookie) throw Error();
        response = await upstreamFetch(resource, {
          method:req.method, redirect:'manual', signal:AbortSignal.timeout(15000),
          headers:{...headers,Cookie:cookie}, ...(body ? {body} : {})
        });
      }
      const contentType = response.headers.get('content-type') || '';
      if (!contentType.includes('application/json') || response.status >= 300 && response.status < 400) {
        return res.status(502).json({error:'O backend Preview não respondeu à API autenticada.'});
      }
      const text = await response.text();
      if (Buffer.byteLength(text) > 512 * 1024) throw Error();
      const data = JSON.parse(text);
      if (path === '/api/health' && data && typeof data === 'object' && data.ok === true) {
        // A UI nunca oferece Gerar enquanto a admissão estiver desligada.
        data.admission_ready = data.ready === true && admissionReady;
      }
      return res.status(response.status).json(data);
    } catch {
      return res.status(502).json({error:'Não foi possível consultar o backend Preview. Tente verificar a conexão novamente.'});
    }
  };
}

module.exports = createHandler();
module.exports.createHandler = createHandler;
