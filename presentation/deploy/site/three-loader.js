/* ===== SYLANNE · Three.js 共享加载器（UMD r137，file:// 友好）=====
   全局单份 three + 可选 GLTFLoader，避免 field3d / model3d 各加载一份导致版本打架。
   window.loadThree()           -> Promise<THREE>
   window.loadThree(true)       -> Promise<THREE>（并确保 THREE.GLTFLoader 就绪）
*/
(function(){
  const THREE_CDN=[
    'assets/vendor/three.min.js',
    'https://registry.npmmirror.com/three/0.137.0/files/build/three.min.js',
    'https://unpkg.com/three@0.137.0/build/three.min.js'
  ];
  const GLTF_CDN=[
    'assets/vendor/GLTFLoader.js',
    'https://registry.npmmirror.com/three/0.137.0/files/examples/js/loaders/GLTFLoader.js',
    'https://unpkg.com/three@0.137.0/examples/js/loaders/GLTFLoader.js'
  ];
  // meshopt 解码器（本地 vendored，内嵌 wasm，无额外 fetch）；模型走 EXT_meshopt_compression 必需
  const MESHOPT=['assets/vendor/meshopt_decoder.js'];
  function script(src){return new Promise((res,rej)=>{const s=document.createElement('script');s.src=src;s.onload=res;s.onerror=rej;document.head.appendChild(s);});}
  function first(urls){return urls.reduce((p,u)=>p.catch(()=>script(u)),Promise.reject());}
  let core=null, gltf=null;
  window.loadThree=function(needGLTF){
    if(!core) core=first(THREE_CDN).then(()=>window.THREE);
    if(!needGLTF) return core;
    // GLTFLoader + meshopt decoder 都就绪后才 resolve；decoder 失败不阻断（退化为无压缩模型仍可加载）
    if(!gltf) gltf=core.then(()=>first(GLTF_CDN)).then(()=>first(MESHOPT).catch(()=>{})).then(()=>window.THREE);
    return gltf;
  };
})();
