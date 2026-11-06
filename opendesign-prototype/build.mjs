import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';
const root=fileURLToPath(new URL('.',import.meta.url));
const target=join(root,'index.html');
if(existsSync(target)&&!process.argv.includes('--replace-generated'))throw new Error('index.html 已存在。若已在 OpenDesign 编辑，请先另存；确认覆盖生成版时加 --replace-generated。');
const html=readFileSync(join(root,'src/page.html'),'utf8').replace('/* BUILD:STYLE */',()=>readFileSync(join(root,'src/style.css'),'utf8')).replace('/* BUILD:MODEL */',()=>readFileSync(join(root,'src/model.js'),'utf8')).replace('/* BUILD:SCRIPT */',()=>readFileSync(join(root,'src/app.js'),'utf8'));
writeFileSync(target,html);console.log('已生成独立 HTML：'+target);

