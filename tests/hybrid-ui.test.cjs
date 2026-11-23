const {test}=require('node:test');
const assert=require('node:assert/strict');
const {readFileSync}=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');

const app=readFileSync(path.join(__dirname,'..','web','app.js'),'utf8');

test('hosted frontend source is valid JavaScript and selects loopback-only local worker',()=>{
  assert.doesNotThrow(()=>new vm.Script(app,{filename:'web/app.js'}));
  assert.match(app,/const localWorkerMode=!localMode/);
  assert.match(app,/const LOCAL_WORKER_URL='http:\/\/127\.0\.0\.1:8765'/);
  assert.match(app,/if\(localWorkerMode\)\{await connectLocalWorker\(\);return;\}/);
});

test('hosted local processing skips Cloud API credentials and preserves local downloads',()=>{
  assert.match(app,/function authHeaders\(\)\{return \{\};\}/);
  assert.match(app,/if\(!localProcessing && clip\.download_endpoint\)/);
  assert.match(app,/if\(localProcessing\)\{/);
  assert.match(app,/video\.src=safePath\(clip\.name\)\+'\?inline=1'/);
  assert.match(app,/a\.href=localProcessing\?safePath\(job\.zip_name\)/);
});

test('mobile browser accepts only the exact private Tailscale HTTPS form',()=>{
  const start=app.indexOf('function parseWorkerEndpoint(');
  const end=app.indexOf('async function connectLocalWorker()',start);
  assert.ok(start>0 && end>start);
  const parse=new Function(app.slice(start,end)+'\nreturn parseWorkerEndpoint;')();
  assert.equal(parse('http://127.0.0.1:8765'),'http://127.0.0.1:8765');
  assert.equal(parse('https://arch.my-tailnet.ts.net/'),'https://arch.my-tailnet.ts.net');
  for(const bad of [
    'http://192.168.0.1:8765','http://example.com:8765',
    'https://other.example.com','https://a.ts.net',
    'https://arch.my-tailnet.ts.net:8443',
    'https://admin@arch.my-tailnet.ts.net',
    'https://arch.my-tailnet.ts.net/bad','https://arch.my-tailnet.ts.net?next=1',
    'https://arch.my-tailnet.ts.net/#fragment'
  ]) assert.throws(()=>parse(bad),{message:/Use http/});
});
