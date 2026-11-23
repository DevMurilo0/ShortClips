const {test}=require('node:test');
const assert=require('node:assert/strict');
const {readFileSync}=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

const app=readFileSync(path.join(__dirname,'..','web','app.js'),'utf8');
const build=readFileSync(path.join(__dirname,'..','scripts','build_static.mjs'),'utf8');

test('same approved design remains valid, remote Owner mode hides API key',()=>{
 assert.doesNotThrow(()=>new vm.Script(app));
 assert.match(app,/const cloudProduction=window\.SHORTFORGE_IS_PRODUCTION===true/);
 assert.match(app,/\$\('backendAccessKey'\)\.hidden=true/);
 assert.match(app,/if\(previewProxy\)\{panel\.hidden=false;await connectPreview\(\);return;\}/);
 assert.match(app,/!cloudProduction && !selectedBox/);
});
test('Production frontend uses private same-origin function; not third-party API key in public assets',()=>{
 assert.match(build,/\['preview','production'\]\.includes\(process\.env\.VERCEL_ENV\)/);
 assert.match(build,/window\.SHORTFORGE_IS_PRODUCTION/);
 assert.doesNotMatch(build,/SHORTFORGE_PREVIEW_ACCESS_KEY|SHORTFORGE_OWNER_ACCESS_KEY|SHORTFORGE_BACKEND_PROTECTION_BYPASS/);
 assert.match(app,/\/api\/backend\?path=/);
 assert.match(app,/function authHeaders\(\)\{return !localMode&&!previewProxy&&apiKey/);
});

test('merged main HTML retains usage panel, permission and 30-second source options',()=>{
 const html=readFileSync(path.join(__dirname,'..','web','index.html'),'utf8');
 const ids=[...new Set([...app.matchAll(/\$\('([^']+)'\)/g)].map(m=>m[1]))];
 for(const id of ids)assert.match(html,new RegExp('id=["\\x27]'+id+'["\\x27]'), 'missing form element '+id);
 assert.match(html,/id="usagePanel"/);
 assert.match(html,/id="rightsConfirmed"[^>]*required/);
 assert.match(html,/value="30" selected>30 segundos/);
 assert.doesNotMatch(html,/value="https:\/\/youtu\.be\/yWvnOWILFk0"/);
});
