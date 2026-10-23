// Offline Chrome/Edge interaction verification via the browser's local DevTools protocol.
import fs from 'node:fs/promises';
import path from 'node:path';
import {spawn} from 'node:child_process';
import {pathToFileURL} from 'node:url';
const [htmlArg,outArg,executable='C:/Program Files/Google/Chrome/Application/chrome.exe']=process.argv.slice(2);
if(!htmlArg||!outArg)throw new Error('Usage: node browser_demo_test.mjs HTML NEW_OUTPUT_DIRECTORY [CHROME_EXE]');
const out=path.resolve(outArg);await fs.mkdir(out,{recursive:false});
const profile=path.join(out,'browser_profile');await fs.mkdir(profile);
const browserLog=await fs.open(path.join(out,'browser_console.log'),'wx');
const browser=spawn(executable,['--headless=new','--no-sandbox','--disable-gpu','--enable-logging=stderr','--remote-debugging-port=0','--remote-debugging-address=127.0.0.1',`--user-data-dir=${profile}`,'--no-first-run','--no-default-browser-check','--disable-background-networking','--disable-sync','--disable-extensions','--disable-component-update','--window-size=1500,1100',pathToFileURL(path.resolve(htmlArg)).href],{windowsHide:true,stdio:['ignore','ignore',browserLog.fd]});
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
let socket;const pending=new Map();let id=0;const errors=[],checks=[];
const keepalive=setInterval(()=>{},1000);
browser.on('exit',(code,signal)=>console.log('BROWSER_EXIT',code,signal));
function assert(condition,message){if(!condition)throw new Error(message);checks.push(message)}
try{
 let port;
 for(let i=0;i<100;i++){try{port=Number((await fs.readFile(path.join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0]);break}catch{await sleep(100)}}
 if(!port)throw new Error('Browser did not expose its local DevTools port');
 const protocol=await (await fetch(`http://127.0.0.1:${port}/json/protocol`)).json();
 await fs.writeFile(path.join(out,'browser_protocol_version.json'),JSON.stringify(protocol.version));
 const targets=await (await fetch(`http://127.0.0.1:${port}/json`)).json();
 const target=targets.find(t=>t.type==='page');if(!target)throw new Error('No page target');
 socket=new WebSocket(target.webSocketDebuggerUrl);await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject});
 socket.onclose=e=>{for(const p of pending.values()){clearTimeout(p.timer);p.reject(new Error('DevTools closed '+e.code+' '+e.reason))}pending.clear()};
 socket.onerror=e=>console.error('WEBSOCKET_ERROR',e.message);
 socket.onmessage=event=>{const m=JSON.parse(event.data);if(m.id){const p=pending.get(m.id);if(p){pending.delete(m.id);clearTimeout(p.timer);m.error?p.reject(new Error(JSON.stringify(m.error))):p.resolve(m.result)}}else if(m.method==='Runtime.exceptionThrown')errors.push(m.params)};
 function send(method,params={}){return new Promise((resolve,reject)=>{const key=++id;const timer=setTimeout(()=>{pending.delete(key);reject(new Error('DevTools timeout '+method))},10000);pending.set(key,{resolve,reject,timer});socket.send(JSON.stringify({id:key,method,params}))})}
 async function evaluate(expression){const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw new Error(JSON.stringify(r.exceptionDetails));return r.result.value}
 await send('Runtime.enable');await send('Page.enable');await send('Network.enable');await send('Network.emulateNetworkConditions',{offline:true,latency:0,downloadThroughput:0,uploadThroughput:0});await send('Emulation.setDeviceMetricsOverride',{width:1500,height:1100,deviceScaleFactor:1,mobile:false});
 for(let i=0;i<100;i++){if(await evaluate('!!window.demoState'))break;await sleep(100)}
 assert(await evaluate('!!window.demoState'),'real page loaded and rendered');
 async function choose(id,value){await evaluate(`document.getElementById(${JSON.stringify(id)}).value=${JSON.stringify(value)};document.getElementById(${JSON.stringify(id)}).dispatchEvent(new Event('change',{bubbles:true}));true`)}
 async function click(selector){const box=await evaluate(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});e.scrollIntoView({block:'nearest'});const r=e.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()`);await send('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...box});await send('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,...box})}
 async function snapshot(name){const r=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:true});await fs.writeFile(path.join(out,name),Buffer.from(r.data,'base64'))}
 const expected=await evaluate(`data.cases.map(c=>({seed:c.seed,scenario:c.scenario,methods:Object.fromEntries(Object.entries(c.methods).map(([k,m])=>[k,{initial:m.initial_metrics,replanned:m.replanned_metrics}]))}))`);
 for(const c of expected){await choose('scenario',c.scenario);await choose('seed',String(c.seed));for(const method of ['baseline','improved']){await choose('method',method);for(const view of [0,1,2]){await click(`[data-view="${view}"]`);const actual=await evaluate('window.demoState'),metric=c.methods[method][view===2?'replanned':'initial'];assert(actual.score===metric.task_score&&actual.coverage===metric.coverage&&actual.violations===0,`${c.scenario} seed${c.seed} ${method} view${view} matches independent metrics`)}}}
 await choose('scenario','early');await choose('seed','17');await choose('method','improved');await click('[data-view="0"]');await snapshot('01_seed17_improved_overview.png');
 await choose('scenario','late');await choose('method','baseline');await click('[data-view="1"]');await click('#zoom');
 assert(await evaluate('document.getElementById("seed").disabled && window.demoState.seed===42'),'late scenario is restricted to seed42');
 assert(await evaluate('window.demoState.zoom && document.querySelectorAll("#timeline .task").length>0'),'fault detail zoom renders actual tasks');
 await click('#timeline .task');assert((await evaluate('document.getElementById("task-detail").textContent')).includes('UTC 开始'),'task click reveals actual details');
 await snapshot('02_late_fault_history.png');
 await click('#step');assert((await evaluate('window.demoState.view'))===2,'step advances to replanned view');
 await snapshot('03_late_replanned.png');
 await click('#play');const before=await evaluate('window.demoState.view');await sleep(2100);assert((await evaluate('window.demoState.view'))!==before,'playback advances views');await click('#play');const paused=await evaluate('window.demoState.view');await sleep(2000);assert((await evaluate('window.demoState.view'))===paused,'pause stops playback');
 await send('Emulation.setDeviceMetricsOverride',{width:600,height:1000,deviceScaleFactor:1,mobile:false});
 assert(await evaluate('document.documentElement.scrollWidth<=innerWidth'),'narrow layout has no document-level horizontal overflow');
 assert(errors.length===0,'no browser runtime exceptions');
 await fs.writeFile(path.join(out,'browser_checks.json'),JSON.stringify({status:'PASS',browser:'local installed Chrome/Edge',offline_file_url:target.url,checks,screenshots:['01_seed17_improved_overview.png','02_late_fault_history.png','03_late_replanned.png'],runtime_errors:errors},null,2));
 console.log(JSON.stringify({status:'PASS',checks:checks.length,output:out}));
 await send('Browser.close').catch(()=>{});
}catch(error){await fs.writeFile(path.join(out,'browser_checks.json'),JSON.stringify({status:'FAIL',reason:String(error),checks,runtime_errors:errors},null,2));console.error(error);process.exitCode=2}
finally{clearInterval(keepalive);for(const p of pending.values())clearTimeout(p.timer);if(socket)socket.close();browser.kill();await browserLog.close()}
