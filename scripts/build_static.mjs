// Static copy is optional and cannot execute or connect to a cloud backend.
import {mkdir, copyFile, writeFile} from 'node:fs/promises';
await mkdir('public', {recursive:true});
for(const file of ['index.html','app.js','style.css']) await copyFile('web/'+file,'public/'+file);
await writeFile('public/config.js','// Local-only; no remote API configuration.\n','utf8');
console.log('Static interface only. Start ./iniciar.sh for processing.');
