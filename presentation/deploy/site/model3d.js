/* ===== SYLANNE · 载体页 3D 角色模型（Three.js UMD + 全局 GLTFLoader）=====
   classic script，走 window.loadThree(true)（共享单份 three r137），file:// 友好。
   首次进「载体」视图才加载 assets/sylanne.glb（换模型只替该文件）。
   缓慢自转 + 鼠标拖拽转视角 + hover 跟随 + 呼吸浮动 + 藕荷灯（主题联动）。
   无 WebGL / 加载失败 → 保留 .model-fallback 脉冲环。
*/
(function(){
  let booted=false;
  let onView=(document.body.getAttribute('data-view')||'')==='embodiment';
  addEventListener('sylanne:view', e=>{
    const here=(e.detail&&e.detail.name)==='embodiment';
    onView=here;
    if(here&&!booted){ booted=true; boot(); }
    else if(here&&booted&&window.__model3dResume){ window.__model3dResume(); }  // 回到载体页：恢复循环
  });

  function boot(){
    const wrap=document.querySelector('.ph-model');
    const canvas=document.getElementById('model3d');
    if(!wrap||!canvas||!window.loadThree) return;
    try{const t=document.createElement('canvas');if(!(t.getContext('webgl')||t.getContext('experimental-webgl')))return;}catch(_){return;}
    window.loadThree(true).then(run).catch(()=>{});

    function run(THREE){
      if(!THREE||!THREE.GLTFLoader) return;
      const cssVar=(n,f)=>getComputedStyle(document.documentElement).getPropertyValue(n).trim()||f;

      const renderer=new THREE.WebGLRenderer({canvas,alpha:true,antialias:true});
      renderer.setPixelRatio(Math.min(devicePixelRatio||1,2));
      if('outputEncoding' in renderer) renderer.outputEncoding=THREE.sRGBEncoding;

      const scene=new THREE.Scene();
      const camera=new THREE.PerspectiveCamera(35,1,0.1,100);
      camera.position.set(0,0,5);

      const key=new THREE.DirectionalLight(new THREE.Color(cssVar('--accent','#b88a9e')),2.2); key.position.set(2,3,4); scene.add(key);
      const fill=new THREE.DirectionalLight(new THREE.Color(cssVar('--cyan','#4fd4e0')),0.7); fill.position.set(-3,1,2); scene.add(fill);
      const rim=new THREE.DirectionalLight(0xffffff,1.0); rim.position.set(0,2,-4); scene.add(rim);
      const front=new THREE.DirectionalLight(0xffffff,1.4); front.position.set(0,0.5,6); scene.add(front); // 正面补光，照亮脸
      scene.add(new THREE.HemisphereLight(0xffffff,0x4a3a44,1.1));  // 天顶白/地面暗藕荷，救 PBR 发暗
      scene.add(new THREE.AmbientLight(0xffffff,0.85));

      const pivot=new THREE.Group(); scene.add(pivot);
      const FRONT=Math.PI*1.5;   // 该 glb 转正后正面朝向（脸+眼镜对相机）
      let mixer=null, py=0;

      function fit(r){renderer.setSize(r.width,r.height,false);camera.aspect=r.width/r.height;camera.updateProjectionMatrix();}

      const loader=new THREE.GLTFLoader();
      if(window.MeshoptDecoder) loader.setMeshoptDecoder(window.MeshoptDecoder);  // 模型走 meshopt 几何压缩，必须挂解码器
      loader.load('assets/sylanne.glb', gltf=>{
        const model=gltf.scene;
        model.rotation.x=-Math.PI/2;                 // GLB 是 Z-up（VAST AIGC 导出），转正成站立 Y-up
        model.updateMatrixWorld(true);
        const box=new THREE.Box3().setFromObject(model);
        const c=box.getCenter(new THREE.Vector3()), s=box.getSize(new THREE.Vector3());
        model.position.sub(c);
        const scale=2.5/Math.max(s.x,s.y,s.z); model.scale.setScalar(scale);
        pivot.add(model);
        wrap.classList.add('loaded'); canvas.classList.add('on');
        if(gltf.animations && gltf.animations.length){mixer=new THREE.AnimationMixer(model);mixer.clipAction(gltf.animations[0]).play();}
        fit(wrap.getBoundingClientRect());
      }, undefined, ()=>{/* 失败：保留兜底环 */});

      new MutationObserver(()=>{key.color.set(cssVar('--accent','#b88a9e'));fill.color.set(cssVar('--cyan','#4fd4e0'));})
        .observe(document.documentElement,{attributes:true,attributeFilter:['data-theme']});

      let drag=false,px=0,tY=FRONT,tX=0.05,curY=FRONT,curX=0.05;  // 初始正面朝前（脸对相机）
      canvas.addEventListener('pointerdown',e=>{drag=true;px=e.clientX;py=e.clientY;canvas.setPointerCapture(e.pointerId);});
      canvas.addEventListener('pointermove',e=>{if(!drag)return;tY+=(e.clientX-px)*0.01;tX+=(e.clientY-py)*0.006;tX=Math.max(-0.5,Math.min(0.5,tX));px=e.clientX;py=e.clientY;});
      canvas.addEventListener('pointerup',()=>{drag=false;});
      wrap.addEventListener('mousemove',e=>{if(drag)return;const r=wrap.getBoundingClientRect();tY=FRONT+((e.clientX-r.left)/r.width-0.5)*0.7;tX=0.05+((e.clientY-r.top)/r.height-0.5)*0.35;});
      wrap.addEventListener('mouseleave',()=>{tY=FRONT;tX=0.05;});

      const resize=()=>fit(wrap.getBoundingClientRect());
      fit(wrap.getBoundingClientRect()); addEventListener('resize',resize);

      const clock=new THREE.Clock(); let t=0; let looping=false;
      function frame(){
        if(!onView){looping=false;return;}        // 离开载体页：停循环
        if(document.hidden){setTimeout(frame,400);return;}
        looping=true;
        requestAnimationFrame(frame);
        const dt=clock.getDelta(); t+=dt;
        if(mixer)mixer.update(dt);
        if(!drag)tY=FRONT+Math.sin(t*0.35)*0.32;   // 正面 ±18° 轻摆，始终对着你
        curY+=(tY-curY)*0.08; curX+=(tX-curX)*0.08;
        pivot.rotation.y=curY; pivot.rotation.x=curX;
        pivot.position.y=Math.sin(t*1.1)*0.05;
        renderer.render(scene,camera);
      }
      window.__model3dResume=()=>{ if(!looping){clock.getDelta();requestAnimationFrame(frame);} };
      frame();
    }
  }
})();
