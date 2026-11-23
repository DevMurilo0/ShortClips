// Build sem framework: somente a interface vai para o deploy, não os vídeos,
// modelos, código Python nem resultados de usuários.
import {mkdir, copyFile, writeFile} from 'node:fs/promises';
const url=(process.env.SHORTFORGE_PUBLIC_API_URL || '').trim().replace(/\/$/, '');
if(url && (!/^https:\/\//.test(url) || new URL(url).pathname !== '/')){
  throw new Error('SHORTFORGE_PUBLIC_API_URL precisa ser uma URL HTTPS na raiz do domínio.');
}
await mkdir('public', {recursive:true});
for(const file of ['index.html','app.js','style.css']){
  await copyFile('web/'+file,'public/'+file);
}
await writeFile('public/config.js',
  'window.SHORTFORGE_API_URL = ' + JSON.stringify(url) + ';\n' +
  'window.SHORTFORGE_PREVIEW_PROXY = ' + JSON.stringify(process.env.VERCEL_ENV === 'preview') + ';\n','utf8');
console.log('Frontend estático pronto em public/. API configurada: '+(url||'não'));
