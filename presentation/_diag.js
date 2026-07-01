// CDP diag using Node 22 built-in WebSocket + fetch — no deps
const PORT=9223, URL='http://127.0.0.1:8099/index.html#/embodiment';
(async()=>{
  const list=await (await fetch(`http://127.0.0.1:${PORT}/json`)).json();
  let tgt=list.find(t=>t.type==='page')||list[0];
  const ws=new WebSocket(tgt.webSocketDebuggerUrl);
  let id=0; const pend=new Map();
  const send=(m,p={})=>{const i=++id;ws.send(JSON.stringify({id:i,method:m,params:p}));return new Promise(r=>pend.set(i,r));};
  const logs=[];
  await new Promise(r=>ws.addEventListener('open',r));
  ws.addEventListener('message',ev=>{
    const m=JSON.parse(ev.data);
    if(m.id&&pend.has(m.id)){pend.get(m.id)(m.result);pend.delete(m.id);return;}
    if(m.method==='Runtime.consoleAPICalled'){const a=(m.params.args||[]).map(x=>x.value??x.description??x.type).join(' ');logs.push('['+m.params.type+'] '+a);}
    if(m.method==='Log.entryAdded'){const e=m.params.entry;logs.push('[log:'+e.level+'] '+e.text+(e.url?' @'+e.url:''));}
    if(m.method==='Runtime.exceptionThrown'){const d=m.params.exceptionDetails;logs.push('[EXC] '+(d.exception?.description||d.text));}
    if(m.method==='Network.loadingFailed'){logs.push('[NETFAIL] '+m.params.errorText+' type='+m.params.type);}
    if(m.method==='Network.responseReceived'){const r=m.params.response;if(r.url.match(/\.(glb|js)(\?|$)/)&&(r.status>=400||r.status===0))logs.push('[HTTP '+r.status+'] '+r.url);}
  });
  await send('Runtime.enable');await send('Log.enable');await send('Network.enable');await send('Page.enable');
  await send('Page.navigate',{url:'about:blank'});
  await new Promise(r=>setTimeout(r,500));
  await send('Page.navigate',{url:URL});
  await new Promise(r=>setTimeout(r,8000));  // let embodiment view + model load
  // probe state
  const probe=await send('Runtime.evaluate',{expression:`JSON.stringify({hasLoadThree:typeof window.loadThree,THREE:typeof window.THREE,GLTF:(window.THREE&&!!window.THREE.GLTFLoader),phModel:!!document.querySelector('.ph-model'),loaded:!!document.querySelector('.ph-model.loaded'),canvasOn:!!document.querySelector('#model3d.on')})`,returnByValue:true});
  console.log('STATE:',probe.result.value);
  console.log('--- console/network ---');
  console.log(logs.join('\n')||'(no logs captured)');
  ws.close();process.exit(0);
})().catch(e=>{console.error('DIAG ERR',e.message);process.exit(1)});
