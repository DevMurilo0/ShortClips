const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const js=fs.readFileSync('web/app.js','utf8');
const html=fs.readFileSync('web/index.html','utf8');
function boot(hostname){
  const nodes=new Map(), calls=[];
  function node(id){if(!nodes.has(id))nodes.set(id,{hidden:false,disabled:false,addEventListener(){}});return nodes.get(id)}
  const context={location:{hostname},document:{getElementById:node},fetch:async(path)=>{calls.push(path);return {ok:true,json:async()=>({job:null})}},AbortSignal,console};
  vm.createContext(context);
  new vm.Script(js).runInContext(context);
  return {nodes,calls,context};
}
test('localhost restores latest task without cloud configuration',()=>{
  const {nodes,calls}=boot('127.0.0.1');
  assert.equal(nodes.get('backendPanel').hidden,true);
  assert.equal(nodes.get('submit').disabled,false);
  assert.deepEqual(calls,['/api/jobs/latest']);
});
test('hosted interface does not contact any API or enable generation',()=>{
  const {nodes,calls,context}=boot('example.vercel.app');
  assert.equal(nodes.get('backendPanel').hidden,false);
  assert.equal(nodes.get('submit').disabled,true);
  assert.deepEqual(calls,[]);
  assert.throws(()=>vm.runInContext("apiPath('/api/jobs')",context),/computador/);
});
test('five cuts are default and facecam, captions, MP4 and ZIP are preserved',()=>{
  assert.match(html,/<option selected>5<\/option>/);
  assert.match(html,/value="auto" selected/);
  assert.match(html,/id="model"/);
  assert.match(js,/Baixar MP4/);
  assert.match(js,/Baixar todos os Shorts/);
  assert.doesNotMatch(js,/previewProxy|cloudProduction|SHORTFORGE_API_URL|sessionStorage|localStorage/);
});
