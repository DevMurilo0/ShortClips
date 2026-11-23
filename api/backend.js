'use strict';

const ROUTE = /^\/api\/(?:health|usage|jobs(?:\/latest|\/[a-f0-9]{32}(?:\/(?:cancel|retry))?)?|download(?:\?pathname=[^#]+)?)$/;

function createHandler(upstreamFetch = fetch) {
  return async function handler(req, res) {
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('X-Content-Type-Options', 'nosniff');
    const env = process.env;
    if (env.VERCEL_ENV !== 'preview') {
      return res.status(503).json({error:'Integração de Preview não habilitada.'});
    }
    // Aceitar somente o host imutável do Preview protegido, nunca Production.
    const deploymentHost = String(env.VERCEL_URL || req.headers.host || '').toLowerCase();
    if (!/^short-clips-[a-z0-9]+-murilo15\.vercel\.app$/.test(deploymentHost)) {
      return res.status(503).json({error:'Somente o Preview protegido pode acionar o motor.'});
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
    if (createJob && env.SHORTFORGE_PREVIEW_ADMISSION !== '1') {
      return res.status(503).json({error:'Geração pausada: ainda falta ativar a homologação autorizada.'});
    }
    let body;
    if (req.method === 'POST') {
      if (origin !== expectedOrigin) {
        return res.status(403).json({error:'A geração exige acesso pelo Preview autenticado.'});
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
        if (j.rights_confirmed !== true || j.count !== 1 || j.length !== 30 || j.resolution !== 720 ||
            typeof j.url !== 'string' || j.url.length > 2048 ||
            !Array.isArray(box) || box.length !== 4 || !box.every(Number.isFinite) ||
            box[0] < 0 || box[1] < 0 || box[2] <= 0 || box[3] <= 0 ||
            box[0] + box[2] > 100 || box[1] + box[3] > 100) {
          return res.status(400).json({error:'Homologação: apenas um Short de 30s em 720p, com região manual e vídeo autorizado.'});
        }
      }
    }
    let base;
    try {
      base = new URL(env.SHORTFORGE_PUBLIC_API_URL);
      if (base.protocol !== 'https:' || base.username || base.password || base.port ||
          base.pathname !== '/' || base.search || base.hash ||
          !/^backend-short-clips-[a-z0-9]+-murilo15\.vercel\.app$/.test(base.hostname)) throw Error();
    } catch {
      return res.status(503).json({error:'Deployment Preview do backend não configurado.'});
    }
    const key = env.SHORTFORGE_PREVIEW_ACCESS_KEY;
    const share = env.SHORTFORGE_BACKEND_PREVIEW_SHARE;
    if (!key || key.length < 32 || !share || key.includes('[SENSITIVE]') || share.includes('[SENSITIVE]')) {
      return res.status(503).json({error:'Acesso privado ao backend não configurado.'});
    }
    const resource = new URL(path, base);
    const target = new URL(resource);
    // The share is scoped to this immutable deployment, never a project-wide bypass.
    // It stays server-side; no Location, cookies or upstream URLs reach the browser.
    target.searchParams.set('_vercel_share', share);
    try {
      const headers = {Accept:'application/json',Authorization:'Bearer ' + key};
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
        data.admission_ready = data.ready === true && env.SHORTFORGE_PREVIEW_ADMISSION === '1';
      }
      return res.status(response.status).json(data);
    } catch {
      return res.status(502).json({error:'Não foi possível consultar o backend Preview. Tente verificar a conexão novamente.'});
    }
  };
}

module.exports = createHandler();
module.exports.createHandler = createHandler;
