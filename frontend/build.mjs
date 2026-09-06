import {readFileSync,mkdirSync,writeFileSync} from 'node:fs';
const raw=process.env.API_BASE_URL;
if(!raw) throw new Error('Set API_BASE_URL to your public HTTPS FastAPI origin.');
const url=new URL(raw);
if(url.protocol!=='https:'||url.username||url.password||url.pathname!=='/'||url.search||url.hash) throw new Error('API_BASE_URL must be an HTTPS origin with no credentials, path or query.');
if(url.hostname==='localhost'||url.hostname==='127.0.0.1'||url.hostname==='[::1]'||url.hostname==='v0.app'||url.hostname.endsWith('.localhost')||url.hostname.startsWith('192.168.')||url.hostname.startsWith('10.')) throw new Error('Use a public backend domain, not a local address.');
const html=readFileSync('index.html','utf8').replace('<meta name="api-base" content="">','<meta name="api-base" content="'+url.origin+'">');
mkdirSync('dist',{recursive:true});writeFileSync('dist/index.html',html);
console.log('Built one HoneyChain frontend with the configured public API origin.');
