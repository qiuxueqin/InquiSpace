import http from 'node:http';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
const file=fileURLToPath(new URL('./index.html',import.meta.url));
const port=Number(process.env.PROTOTYPE_PORT||4173);
http.createServer((req,res)=>{
const url=new URL(req.url,'http://127.0.0.1');
if(url.pathname!=='/'&&url.pathname!=='/index.html'){res.writeHead(404);res.end('Not found');return}
res.writeHead(200,{'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store'});res.end(readFileSync(file));
}).listen(port,'127.0.0.1',()=>console.log('知境交互原型：http://127.0.0.1:'+port));

