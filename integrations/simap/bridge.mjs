// Read-only stdio MCP bridge. No tool names or commands come from tender content.
import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import { fileURLToPath } from 'node:url';
const [tool, raw = '{}'] = process.argv.slice(2);
if (!['search_tenders', 'get_tender_details', 'list_cantons'].includes(tool)) throw Error('Tool not allowed');
const child = spawn(process.execPath, [fileURLToPath(new URL('./node_modules/@digilac/simap-mcp/dist/index.js', import.meta.url))], {stdio: ['pipe', 'pipe', 'pipe']});
let id = 0;
const pending = new Map();
const timer = setTimeout(() => {child.kill(); process.exit(2);}, 55000);
child.stderr.on('data', () => {});
child.on('error', () => {clearTimeout(timer); process.exit(2);});
const lines = createInterface({input: child.stdout});
lines.on('line', line => {try {const data = JSON.parse(line); const p = pending.get(data.id); if (p) {pending.delete(data.id); data.error ? p.reject(Error(data.error.message)) : p.resolve(data.result);}} catch {}});
function send(method, params) {const n = ++id; return new Promise((resolve, reject) => {pending.set(n, {resolve, reject}); child.stdin.write(JSON.stringify({jsonrpc:'2.0', id:n, method, params})+'\n');});}
try {
 await send('initialize', {protocolVersion:'2024-11-05', capabilities:{}, clientInfo:{name:'tender-opportunity-ui', version:'1.0'}});
 child.stdin.write(JSON.stringify({jsonrpc:'2.0', method:'notifications/initialized'})+'\n');
 const result = await send('tools/call', {name:tool, arguments:JSON.parse(raw)});
 process.stdout.write(JSON.stringify(result));
} catch (e) {process.stderr.write(e.message); process.exitCode=1;}
finally {clearTimeout(timer); child.kill(); lines.close();}
