const {test}=require('node:test');
const assert=require('node:assert/strict');
const {createHandler}=require('../api/backend.js');
const baseline={VERCEL_ENV:'preview',VERCEL_URL:'short-clips-test-murilo15.vercel.app',SHORTFORGE_PREVIEW_PROXY:'1',SHORTFORGE_PUBLIC_API_URL:'https://backend-short-clips-test123-murilo15.vercel.app',SHORTFORGE_PREVIEW_ACCESS_KEY:'private-owner-key-with-more-than-32-characters',SHORTFORGE_BACKEND_PREVIEW_SHARE:'private-deployment-share'};
async function call({path='/api/health',method='GET',headers={},env={},response,body}={}){
 const previous={...process.env};Object.assign(process.env,baseline,env);
 const seen=[];const res={headers:{},setHeader(k,v){this.headers[k]=v},status(s){this.code=s;return this},json(x){this.body=x;return this}};
 try{await createHandler(async (...args)=>{seen.push(args);return response||new Response(JSON.stringify({ok:true,ready:false,mode:'disabled'}),{headers:{'content-type':'application/json'}})})({method,headers,query:{path},body},res);}finally{for(const k of Object.keys(process.env))if(!(k in previous))delete process.env[k];Object.assign(process.env,previous)}
 return {res,seen};
}
test('real upstream status contract preserved and private credentials stay server-side',async()=>{
 const {res,seen}=await call();assert.equal(res.code,200);assert.equal(res.body.ready,false);
 assert.equal(seen.length,1);assert.equal(seen[0][1].redirect,'manual');assert.equal(seen[0][1].headers.Authorization,'Bearer '+baseline.SHORTFORGE_PREVIEW_ACCESS_KEY);
 assert.equal(seen[0][0].searchParams.get('_vercel_share'),baseline.SHORTFORGE_BACKEND_PREVIEW_SHARE);
 assert.equal(res.headers['Cache-Control'],'no-store');assert.ok(!JSON.stringify(res).includes(baseline.SHORTFORGE_BACKEND_PREVIEW_SHARE));
});
test('disabled backend errors are not converted into successful jobs',async()=>{
 const {res}=await call({path:'/api/jobs/latest',response:new Response(JSON.stringify({error:'Motor desativado'}),{status:503,headers:{'content-type':'application/json'}})});assert.equal(res.code,503);assert.equal(res.body.error,'Motor desativado');
});
test('Production and unconfigured proxies fail closed',async()=>{
 for(const env of [{VERCEL_ENV:'production'},{SHORTFORGE_PUBLIC_API_URL:'https://127.0.0.1/'},{SHORTFORGE_PUBLIC_API_URL:'https://backend-short-clips.vercel.app'},{SHORTFORGE_PREVIEW_ACCESS_KEY:'[SENSITIVE]'}]){const {res,seen}=await call({env});assert.equal(res.code,503);assert.equal(seen.length,0)}
});
test('arbitrary routes, duplicate query values and SSRF are denied before fetch',async()=>{
 for(const path of ['https://evil.invalid','//evil.invalid','/api/internal/finished','/api/cleanup','/api/jobs/../../cleanup',['/api/health','/api/usage']]){const {res,seen}=await call({path});assert.equal(res.code,400);assert.equal(seen.length,0)}
});
test('cross-origin requests are rejected',async()=>{
 for(const headers of [{origin:'https://evil.invalid'},{'sec-fetch-site':'cross-site'}]){const {res,seen}=await call({headers});assert.equal(res.code,403);assert.equal(seen.length,0)}
});
test('generation is paused before fetch even if backend might become active',async()=>{
 const {res,seen}=await call({method:'POST',path:'/api/jobs'});assert.equal(res.code,503);assert.equal(seen.length,0);
});
test('redirects and HTML protection pages never leak upstream Location or cookies',async()=>{
 for(const response of [new Response('',{status:302,headers:{location:'https://evil.invalid','set-cookie':'private=secret'}}),new Response('<html>SSO</html>',{headers:{'content-type':'text/html'}})]){const {res}=await call({response});assert.equal(res.code,502);assert.equal(res.headers.location,undefined);assert.equal(res.headers['set-cookie'],undefined)}
});

test('share handshake follows only the identical resource on its pinned deployment',async()=>{
 const previous={...process.env};Object.assign(process.env,baseline);
 let calls=[];const res={setHeader(){},status(s){this.code=s;return this},json(x){this.body=x;return this}};
 try{
  await createHandler(async (url,options)=>{
   calls.push({url,options});
   return calls.length===1?new Response('',{status:307,headers:{location:baseline.SHORTFORGE_PUBLIC_API_URL+'/api/health','set-cookie':'_vercel_jwt=server-session; Secure; HttpOnly'}}):new Response('{"ok":true,"ready":false}',{headers:{'content-type':'application/json'}});
  })({method:'GET',headers:{},query:{path:'/api/health'}},res);
 }finally{for(const k of Object.keys(process.env))if(!(k in previous))delete process.env[k];Object.assign(process.env,previous)}
 assert.equal(res.code,200);assert.equal(calls.length,2);assert.equal(calls[1].options.headers.Cookie,'_vercel_jwt=server-session');assert.equal(calls[1].options.redirect,'manual');assert.ok(!JSON.stringify(res.body).includes('server-session'));
});

test('backend health exposes generation readiness only after private admission',async()=>{
 const response=new Response(JSON.stringify({ok:true,ready:true,mode:'sandbox'}),{headers:{'content-type':'application/json'}});
 const paused=await call({response});assert.equal(paused.res.body.admission_ready,false);
 const enabled=await call({response:new Response(JSON.stringify({ok:true,ready:true,mode:'sandbox'}),{headers:{'content-type':'application/json'}}),env:{SHORTFORGE_PREVIEW_ADMISSION:'1'}});
 assert.equal(enabled.res.body.admission_ready,true);
});
test('authenticated owner can submit exactly one bounded 30-second Preview job',async()=>{
 const body={rights_confirmed:true,url:'https://youtu.be/abcdefghijk',count:1,length:30,resolution:720,manual_box:[0,0,50,80],facecam:'auto',model:'base'};
 const {res,seen}=await call({path:'/api/jobs',method:'POST',
  headers:{origin:'https://short-clips-test-murilo15.vercel.app','content-type':'application/json','sec-fetch-site':'same-origin'},
  env:{SHORTFORGE_PREVIEW_ADMISSION:'1'},body,
  response:new Response(JSON.stringify({job:{id:'a'.repeat(32),status:'queued'}}),{status:201,headers:{'content-type':'application/json'}})});
 assert.equal(res.code,201);assert.equal(res.body.job.status,'queued');assert.equal(seen.length,1);
 assert.equal(seen[0][1].method,'POST');
 assert.equal(seen[0][1].headers.Authorization,'Bearer '+baseline.SHORTFORGE_PREVIEW_ACCESS_KEY);
 assert.deepEqual(JSON.parse(seen[0][1].body),body);
 assert.ok(!JSON.stringify(res.body).includes(baseline.SHORTFORGE_PREVIEW_ACCESS_KEY));
});
test('POST requires rights, strict cost limits, matching origin and explicit admission',async()=>{
 const body={rights_confirmed:true,url:'https://youtu.be/abcdefghijk',count:1,length:30,resolution:720,manual_box:[0,0,50,80]};
 const headers={origin:'https://short-clips-test-murilo15.vercel.app','content-type':'application/json'};
 for(const change of [{count:5},{length:45},{resolution:1080},{manual_box:null},{rights_confirmed:false},{manual_box:[75,75,50,50]}]){
   const {res,seen}=await call({method:'POST',path:'/api/jobs',headers,body:{...body,...change},env:{SHORTFORGE_PREVIEW_ADMISSION:'1'}});
   assert.equal(res.code,400);assert.equal(seen.length,0);
 }
 for(const h of [{...headers,origin:'https://other.invalid'},{'content-type':'application/json'}]){
   const {res,seen}=await call({method:'POST',path:'/api/jobs',headers:h,body,env:{SHORTFORGE_PREVIEW_ADMISSION:'1'}});
   assert.equal(res.code,403);assert.equal(seen.length,0);
 }
 const paused=await call({method:'POST',path:'/api/jobs',headers,body});
 assert.equal(paused.res.code,503);assert.equal(paused.seen.length,0);
});
test('cancel stays available after new-job admission is disabled',async()=>{
 const job='a'.repeat(32);
 const {res,seen}=await call({method:'POST',path:'/api/jobs/'+job+'/cancel',
   headers:{origin:'https://short-clips-test-murilo15.vercel.app','content-type':'application/json'},
   body:{},response:new Response(JSON.stringify({job:{id:job,status:'cancelled'}}),{headers:{'content-type':'application/json'}})});
 assert.equal(res.code,200);assert.equal(seen.length,1);assert.equal(seen[0][1].method,'POST');
});
