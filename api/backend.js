'use strict';

const ROUTE = /^\/api\/(?:health|usage|jobs(?:\/latest|\/[a-f0-9]{32}(?:\/(?:cancel|retry))?)?|download(?:\?pathname=[^#]+)?)$/;

function createHandler(upstreamFetch = fetch) {
  return async function handler(req, res) {
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('X-Content-Type-Options', 'nosniff');
    const env = process.env;
    if (env.VERCEL_ENV !== 'preview' || env.SHORTFORGE_PREVIEW_PROXY !== '1') {
      return res.status(503).json({error:'Integração de Preview não habilitada.'});
    }
    const expectedOrigin = 'https://' + env.VERCEL_URL;
    const origin = req.headers.origin;
    if ((origin && origin !== expectedOrigin) || req.headers['sec-fetch-site'] === 'cross-site') {
      return res.status(403).json({error:'Origem não permitida.'});
    }
    if (!['GET', 'POST'].includes(req.method)) {
      return res.status(405).json({error:'Método não permitido.'});
    }
    const path = req.query.path;
    if (typeof path !== 'string' || path.length > 2048 || !ROUTE.test(path)) {
      return res.status(400).json({error:'Rota de API inválida.'});
    }
    if (req.method === 'POST' && !/^\/api\/jobs(?:\/[a-f0-9]{32}\/(?:cancel|retry))?$/.test(path)) {
      return res.status(405).json({error:'Método não permitido nesta rota.'});
    }
    // Admission stays paused even if the backend is accidentally enabled later.
    if (req.method === 'POST') {
      return res.status(503).json({error:'Geração pausada: orçamento e vídeo autorizado ainda precisam de homologação.'});
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
      let response = await upstreamFetch(target, {
        method:'GET', redirect:'manual', signal:AbortSignal.timeout(15000),
        headers:{Accept:'application/json',Authorization:'Bearer ' + key}
      });
      if (response.status >= 300 && response.status < 400) {
        const location = new URL(response.headers.get('location') || '', target);
        if (location.href !== resource.href) throw Error();
        const cookie = response.headers.getSetCookie()
          .map(value => value.split(';', 1)[0])
          .find(value => value.startsWith('_vercel_jwt='));
        if (!cookie) throw Error();
        response = await upstreamFetch(resource, {
          method:'GET', redirect:'manual', signal:AbortSignal.timeout(15000),
          headers:{Accept:'application/json',Authorization:'Bearer ' + key,Cookie:cookie}
        });
      }
      const contentType = response.headers.get('content-type') || '';
      if (!contentType.includes('application/json') || response.status >= 300 && response.status < 400) {
        return res.status(502).json({error:'O backend Preview não respondeu à API autenticada.'});
      }
      const text = await response.text();
      if (Buffer.byteLength(text) > 512 * 1024) throw Error();
      const data = JSON.parse(text);
      return res.status(response.status).json(data);
    } catch {
      return res.status(502).json({error:'Não foi possível consultar o backend Preview. Tente verificar a conexão novamente.'});
    }
  };
}

module.exports = createHandler();
module.exports.createHandler = createHandler;
