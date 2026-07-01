/* ===== SYLANNE · 共振场 + 多智能体 3D 背景（three.js，画在 #bg3d）=====
   忠实于 v2.1.0 载体架构（SelfCore 编排 9 认知 agent + SDK 共振场 kernel）：
   - 中心：7 节点共振场（HDC/门控/伤痕/层析/HGT/边界/表达），全连接耦合，Kuramoto 相位同步，
           全局相干越阈值 → 表达节点「点火」(相变)。这是 SelfCore 的「大脑」。
   - 外圈：9 个认知 agent（情绪/评估/人格/生活/记忆/节奏/主动/社交/对话），各自 perceive→gate→act，
           gate 通过即脉冲点亮、向中心场注入一份 AgentIntent。
   首页鲜明、其它页淡出（opacity 由 CSS data-view / terrain-settled 控制）。标签由 DOM 层投影。
*/
(function(){
  if(!window.loadThree) return;
  // 移动端（窄屏）不启动 3D 共振场：省 GPU/电量，也不加载 three.min.js；
  // 2D 粒子背景（site.js）会继续画当轻量 signature（__field3d 不置位）。
  if(matchMedia('(max-width:760px)').matches) return;
  const canvas=document.getElementById('bg3d'); if(!canvas) return;
  try{const t=document.createElement('canvas');if(!(t.getContext('webgl')||t.getContext('experimental-webgl')))return;}catch(e){return;}
  window.loadThree().then(init).catch(()=>{});

  const cssVar=(n,f)=>getComputedStyle(document.documentElement).getPropertyValue(n).trim()||f;

  // 中心 7 模块：HDC/门控/伤痕/层析/HGT/边界/表达 ｜ 外圈 9 agent：情绪/评估/人格/生活/记忆/节奏/主动/社交/对话
  // （节点以纯视觉呈现，不挂 DOM 标签——signature 只在场本身，保持克制）

  function init(THREE){
    if(!THREE) return;
    const renderer=new THREE.WebGLRenderer({canvas,alpha:true,antialias:false,powerPreference:'low-power'});
    renderer.setPixelRatio(Math.min(devicePixelRatio||1,1.25));
    const scene=new THREE.Scene();
    const camera=new THREE.PerspectiveCamera(45,innerWidth/innerHeight,0.1,100);
    camera.position.set(0,0.6,9.2);

    let ACC,ACCD,SCAR;
    function theme(){ACC=new THREE.Color(cssVar('--accent','#b88a9e'));ACCD=new THREE.Color(cssVar('--accent-d','#9c6c82'));
      SCAR=new THREE.Color(cssVar('--scar','#7a3a52'));}
    theme(); new MutationObserver(theme).observe(document.documentElement,{attributes:true,attributeFilter:['data-theme']});

    const root=new THREE.Group(); scene.add(root);
    root.position.x=2.1;   // 整组推到右半屏，左侧让给左对齐巨标题（去「正中打架」）

    // —— 中心：7 节点 fibonacci 球面 ——
    const NF=7, fpos=[];
    for(let i=0;i<NF;i++){const y=1-(i/(NF-1))*2, rr=Math.sqrt(1-y*y), th=i*2.399963;
      fpos.push(new THREE.Vector3(Math.cos(th)*rr*1.7, y*1.7, Math.sin(th)*rr*1.7));}

    // 节点球 + 相位 —— 7 核固定大基础尺寸，amp 只做轻微呼吸（保证 7 始终读得出，不被动画反转）
    const phase=new Float32Array(NF), amp=new Float32Array(NF).fill(0.5);
    const freq=[0.9,1.15,0.75,1.0,1.25,0.85,1.05];
    for(let i=0;i<NF;i++) phase[i]=Math.random()*6.283;
    const nodeMesh=[];
    const sph=new THREE.SphereGeometry(0.2,18,18);
    for(let i=0;i<NF;i++){
      const m=new THREE.MeshBasicMaterial({color:ACC,transparent:true,opacity:0.9});
      const s=new THREE.Mesh(sph,m); s.position.copy(fpos[i]); root.add(s); nodeMesh.push(s);
    }
    // 全连接拓扑仍在（21 对，驱动 Kuramoto），但渲染上「按相干稀疏点亮」——
    // 不再常驻满网（那是被否过的 AI 网络图长相）；只有强相干的边、或留疤的边才显形。
    const epairs=[];
    for(let i=0;i<NF;i++)for(let j=i+1;j<NF;j++) epairs.push([i,j,{w:0.4+Math.random()*0.2,scar:0}]);
    const eGeo=new THREE.BufferGeometry();
    const eVerts=new Float32Array(epairs.length*6), eCol=new Float32Array(epairs.length*6);
    eGeo.setAttribute('position',new THREE.BufferAttribute(eVerts,3));
    eGeo.setAttribute('color',new THREE.BufferAttribute(eCol,3));
    const eMat=new THREE.LineBasicMaterial({vertexColors:true,transparent:true,opacity:0.85});
    root.add(new THREE.LineSegments(eGeo,eMat));
    let scarCount=0; const SCAR_MAX=8;   // 伤疤永久累积、封顶（webui 式「回不去」）

    // —— 外圈：9 认知 agent，收成一圈紧致轨道（不再甩到屏边散点）——
    const NA=9, apos=[], aMesh=[], aGate=new Float32Array(NA);
    const aSph=new THREE.SphereGeometry(0.1,14,14);
    for(let i=0;i<NA;i++){
      const a=i/NA*6.283, R=2.7;
      const v=new THREE.Vector3(Math.cos(a)*R, Math.sin(a*1.0)*0.45, Math.sin(a)*R*0.92);
      apos.push(v);
      const m=new THREE.MeshBasicMaterial({color:ACCD,transparent:true,opacity:0.7});
      const s=new THREE.Mesh(aSph,m); s.position.copy(v); root.add(s); aMesh.push(s);
    }
    // 不再画 9 条常驻 agent→中心放射线（那是网络图的「放射 spoke」俗套）。
    // agent 与中心的关系只在 gate 通过时由一颗 intent 脉冲粒子瞬时连接——短暂、有意义、不堆成星图。

    // intent 脉冲：agent gate 通过时，一颗粒子从 agent 飞向中心
    const pulses=[];  // {i, t}  i=agent index, t=0..1
    const pGeo=new THREE.SphereGeometry(0.06,8,8);
    const pMat=new THREE.MeshBasicMaterial({color:ACC,transparent:true,opacity:0.95});
    const pulseMesh=[]; for(let k=0;k<NA;k++){const m=new THREE.Mesh(pGeo,pMat.clone());m.visible=false;root.add(m);pulseMesh.push(m);}

    function resize(){renderer.setSize(innerWidth,innerHeight);camera.aspect=innerWidth/innerHeight;camera.updateProjectionMatrix();}
    resize(); addEventListener('resize',resize);
    requestAnimationFrame(()=>canvas.classList.add('on'));

    // 视图门控：场在每一页都当背景，但只有首页满帧满强度。
    // 非首页：降到 ~12fps 漂移 + CSS 压成极淡纹理，省 GPU/CPU、不抢内容。
    let onHome=(document.body.getAttribute('data-view')||'home')==='home';
    let looping=false;
    addEventListener('sylanne:view',e=>{ onHome=(e.detail&&e.detail.name)==='home'; });

    let mx=0,cmx=0, mpx=-1e4,mpy=-1e4;   // mpx/mpy: 鼠标屏幕像素，用于「触碰扰动场」
    addEventListener('mousemove',e=>{mx=(e.clientX/innerWidth-0.5);mpx=e.clientX;mpy=e.clientY;});
    addEventListener('mouseleave',()=>{mpx=mpy=-1e4;});
    const tmp=new THREE.Color(), _mv=new THREE.Vector3(), K=0.06; let t=0, fire=0;
    const reduceStatic=matchMedia('(prefers-reduced-motion:reduce)').matches;

    function frame(){
      if(document.hidden){setTimeout(frame,400);return;}
      looping=true;
      requestAnimationFrame(frame);
      t+=0.016; cmx+=(mx-cmx)*0.03;

      // Kuramoto 相位同步
      const np=new Float32Array(NF);
      for(let i=0;i<NF;i++){let c=0;
        for(const [a,b,e] of epairs){if(a===i)c+=e.w*(1-e.scar)*Math.sin(phase[b]-phase[i]);else if(b===i)c+=e.w*(1-e.scar)*Math.sin(phase[a]-phase[i]);}
        np[i]=phase[i]+(freq[i]+K*c)*0.05; amp[i]+=((0.5+0.5*Math.sin(phase[i]))-amp[i])*0.1;}
      for(let i=0;i<NF;i++) phase[i]=np[i];
      // 全局相干 + 表达点火
      let sx=0,sy=0; for(let i=0;i<NF;i++){sx+=Math.cos(phase[i]);sy+=Math.sin(phase[i]);}
      const R=Math.sqrt(sx*sx+sy*sy)/NF;
      if(R>0.8 && fire<0.05){fire=1; for(let i=0;i<NF;i++) phase[i]+=(Math.random()-0.5)*2.0;}
      fire*=0.94; amp[6]=Math.max(amp[6],fire);
      // 后学习：Hebbian + 偶发伤疤（永久累积、封顶，绝不复原——这才是「回不去」）
      for(const [a,b,e] of epairs){const coh=0.5+0.5*Math.cos(phase[a]-phase[b]); e.w=Math.max(0.05,Math.min(1,e.w+(coh-0.5)*0.0008));}
      if(scarCount<SCAR_MAX && Math.random()<0.0016){
        const cand=epairs.filter(p=>p[2].scar<0.05);
        if(cand.length){cand[(Math.random()*cand.length)|0][2].scar=1; scarCount++;}
      }

      // 节点视觉 + 鼠标「触碰扰动」：靠近的节点被点亮、相位被扰动（感知即扰动）
      // 7 核：固定大基础尺寸(0.9)，amp 只做轻呼吸，永远比 agent 大、读得出「7」
      for(let i=0;i<NF;i++){
        _mv.copy(fpos[i]).applyMatrix4(root.matrixWorld).project(camera);
        const nx=(_mv.x*0.5+0.5)*innerWidth, ny=(-_mv.y*0.5+0.5)*innerHeight;
        const dpx=Math.hypot(nx-mpx, ny-mpy), touch=Math.exp(-dpx/130);   // 130px 影响半径
        if(touch>0.02){ phase[i]+=touch*0.18*Math.sin(t*3+i); amp[i]=Math.max(amp[i],touch); }
        const s=0.9+amp[i]*0.35+(i===6?fire*0.7:0); nodeMesh[i].scale.setScalar(s);
        nodeMesh[i].material.color.copy(i===6&&fire>0.1?SCAR:ACC); nodeMesh[i].material.opacity=0.6+0.35*amp[i];}
      // 边：按相干稀疏点亮——只有强相干 or 留疤的边显形（去满网）。伤疤边永久暗红、更亮、更显眼
      let ei=0; for(const [a,b,e] of epairs){const coh=0.5+0.5*Math.cos(phase[a]-phase[b]);
        const A=fpos[a],B=fpos[b]; eVerts[ei*6]=A.x;eVerts[ei*6+1]=A.y;eVerts[ei*6+2]=A.z;eVerts[ei*6+3]=B.x;eVerts[ei*6+4]=B.y;eVerts[ei*6+5]=B.z;
        if(e.scar>0.05){ tmp.copy(SCAR).multiplyScalar(0.9); }                 // 疤：永久、显眼
        else { const vis=Math.max(0, coh*e.w-0.55)/0.45; tmp.copy(ACC).multiplyScalar(vis*0.85); } // 仅强相干瞬时显形
        for(const o of [0,3]){eCol[ei*6+o]=tmp.r;eCol[ei*6+o+1]=tmp.g;eCol[ei*6+o+2]=tmp.b;} ei++;}
      eGeo.attributes.position.needsUpdate=true; eGeo.attributes.color.needsUpdate=true;

      // agent gate：随机门控通过 → 发 intent 脉冲飞向中心（agent 缩放 clamp，永不超过核）
      for(let i=0;i<NA;i++){
        aGate[i]*=0.95;
        if(Math.random()<0.004 && !pulseMesh[i].visible){pulseMesh[i].visible=true;pulseMesh[i].userData.t=0;aGate[i]=1;}
        aMesh[i].scale.setScalar(0.85+aGate[i]*0.4); aMesh[i].material.opacity=0.45+0.4*aGate[i];
        const m=pulseMesh[i];
        if(m.visible){m.userData.t+=0.03; const tt=m.userData.t; if(tt>=1){m.visible=false;}
          else m.position.lerpVectors(apos[i], fpos[i%NF], tt);}
      }

      root.rotation.y+=0.0015; root.rotation.x=Math.sin(t*0.1)*0.06;
      camera.position.x=cmx*0.8; camera.lookAt(0.9,0,0);   // 看向偏右的场中心
      renderer.render(scene,camera);
      if(!window.__field3d) window.__field3d=true;
    }
    // prefers-reduced-motion：渲染一帧静态共振场就停，不持续动画
    if(matchMedia('(prefers-reduced-motion:reduce)').matches){
      for(let i=0;i<NF;i++){nodeMesh[i].scale.setScalar(1);nodeMesh[i].material.opacity=0.85;}
      let ei=0; for(const [a,b]of epairs){const A=fpos[a],B=fpos[b];
        eVerts[ei*6]=A.x;eVerts[ei*6+1]=A.y;eVerts[ei*6+2]=A.z;eVerts[ei*6+3]=B.x;eVerts[ei*6+4]=B.y;eVerts[ei*6+5]=B.z;
        // 静态：只显小半数边，避免满网；藕荷淡
        const show=((a*7+b)%3===0); tmp.copy(ACC).multiplyScalar(show?0.6:0);
        for(const o of [0,3]){eCol[ei*6+o]=tmp.r;eCol[ei*6+o+1]=tmp.g;eCol[ei*6+o+2]=tmp.b;}ei++;}
      eGeo.attributes.position.needsUpdate=true;eGeo.attributes.color.needsUpdate=true;
      camera.lookAt(0.9,0,0);renderer.render(scene,camera);window.__field3d=true;return;
    }
    frame();
  }
})();
