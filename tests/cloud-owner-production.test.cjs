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
