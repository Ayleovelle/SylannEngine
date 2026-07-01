/* ===== SYLANNE Project · SPA + Scroll-scrubbed cinematic (GSAP+Lenis) ===== */
const root=document.documentElement;
const reduceMotion=matchMedia('(prefers-reduced-motion:reduce)').matches;

/* —— 主题：auto / light / dark 三态，auto 跟随系统并实时响应 —— */
const themeTg=document.getElementById('themeTg');
const mq=matchMedia('(prefers-color-scheme:dark)');
function applyTheme(){
  const mode=localStorage.getItem('sylanne_theme_mode')||'auto';
  const t=(mode==='auto')?(mq.matches?'dark':'light'):mode;
  root.setAttribute('data-theme',t);root.setAttribute('data-theme-mode',mode);
  if(themeTg){const ic={auto:'◐',light:'☀',dark:'☾'}[mode];const tx={auto:'跟随系统',light:'浅色',dark:'深色'}[mode];
    themeTg.querySelector('.tg-ico').textContent=ic;themeTg.title=(getLang()==='en'?'Theme: ':'主题：')+(getLang()==='en'?{auto:'Auto',light:'Light',dark:'Dark'}[mode]:tx);}
  if(typeof rerenderMermaidForTheme==='function')setTimeout(rerenderMermaidForTheme,60);
}
if(themeTg)themeTg.onclick=()=>{const order=['auto','light','dark'];const cur=localStorage.getItem('sylanne_theme_mode')||'auto';
  localStorage.setItem('sylanne_theme_mode',order[(order.indexOf(cur)+1)%3]);applyTheme();};
mq.addEventListener('change',()=>{if((localStorage.getItem('sylanne_theme_mode')||'auto')==='auto')applyTheme();});

/* —— 国际化 zh↔en：文本节点字典替换，缓存原文可逆 —— */
const DICT=window.I18N||{};
function getLang(){return root.getAttribute('data-lang')==='en'?'en':'zh';}
let i18nWalked=false;
function applyLang(){
  const en=getLang()==='en';
  // 遍历可见文本节点；首次缓存中文原文到 dataset
  const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT,{
    acceptNode(n){const p=n.parentElement;if(!p)return 2;
      if(p.closest('script,style,#boot,.mermaid,.code,.pincount,.split-chars,.reveal-lines,.hero h1,.pagehead h1,[data-tex]'))return 2;
      if(!n.nodeValue||!n.nodeValue.trim())return 2;return 1;}});
  const nodes=[];while(walker.nextNode())nodes.push(walker.currentNode);
  nodes.forEach(n=>{
    const raw=n.nodeValue;
    const lead=raw.slice(0,raw.length-raw.trimStart().length), tail=raw.slice(raw.trimEnd().length);
    if(!n.__zh){n.__zh=raw;n.__key=raw.trim().replace(/\s+/g,' ');}  // 归一化 key：内部空白折叠成单空格
    if(en){const tr=DICT[n.__key];if(tr)n.nodeValue=lead+tr+tail;}
    else{n.nodeValue=n.__zh;}
  });
  // lang 按钮文字 + 文档 lang
  const lt=document.getElementById('langTg');if(lt)lt.textContent=en?'EN':'中';
  root.setAttribute('lang',en?'en':'zh-CN');
  document.title=en?'SYLANNE — Affective Dynamics Engine':'SYLANNE — 情感动力学引擎';
  // 带 data-en-h1 的展示大标题（如 roadmap 的「演化路线」）随语言切换，中文走 split 排除不被遍历，这里专门处理
  document.querySelectorAll('h1[data-en-h1]').forEach(h=>{
    if(!h.dataset.zhH1)h.dataset.zhH1=h.innerHTML;
    h.innerHTML=en?h.dataset.enH1:h.dataset.zhH1;
  });
  // mermaid 图随语言重渲染（图内标签走 MERMAID_EN）
  if(typeof mermaidLib!=='undefined'&&mermaidLib){const v=document.querySelector('.view.active');
    if(v&&v.querySelector('.mermaid'))renderMermaid(v);}
  i18nWalked=true;
}
const langTg=document.getElementById('langTg');
if(langTg)langTg.onclick=()=>{
  if(root.classList.contains('lang-swapping'))return;        // 防连点
  const en=getLang()==='en';const next=en?'zh':'en';
  const commit=()=>{root.setAttribute('data-lang',next);localStorage.setItem('sylanne_lang',next);applyLang();applyTheme();};
  if(reduceMotion){commit();return;}                               // 尊重 reduced-motion：直接换
  root.classList.add('lang-swapping');                       // 淡出
  setTimeout(()=>{commit();                                  // 中点换字（此刻不可见）
    requestAnimationFrame(()=>root.classList.remove('lang-swapping'));}, 270);  // 淡入
};

const nav=document.getElementById('nav');
const burger=document.getElementById('burger'),links=document.getElementById('links');
/* —— 汉堡菜单：aria-expanded / Escape / outside-click / 焦点回收 —— */
function closeMenu(){ if(!links)return; links.classList.remove('open'); if(burger)burger.setAttribute('aria-expanded','false'); }
function openMenu(){ if(!links)return; links.classList.add('open'); if(burger){burger.setAttribute('aria-expanded','true');
  const f=links.querySelector('a,button'); if(f)try{f.focus({preventScroll:true});}catch(e){}} }
if(burger&&links){
  burger.setAttribute('aria-expanded','false');burger.setAttribute('aria-controls','links');
  burger.onclick=e=>{e.stopPropagation();links.classList.contains('open')?closeMenu():openMenu();};
  links.querySelectorAll('a[data-nav]').forEach(a=>a.onclick=()=>closeMenu());
  document.addEventListener('click',e=>{ if(!links.classList.contains('open'))return;        // outside click 关闭
    if(e.target.closest('#links,#burger'))return; closeMenu(); });
  document.addEventListener('keydown',e=>{ if(e.key==='Escape'&&links.classList.contains('open')){closeMenu();
    try{burger.focus({preventScroll:true});}catch(_){}} });                                   // Escape 关闭并把焦点还给 burger
  matchMedia('(min-width:921px)').addEventListener('change',()=>closeMenu());                 // 桌面⇄移动切换时清残留 .open
}

/* —— 视图 / 路由状态 —— */
const views=[...document.querySelectorAll('.view')];
const routebar=document.createElement('div');routebar.id='routebar';document.body.appendChild(routebar);
function curHash(){const m=(location.hash||'').match(/#\/([a-z]+)/);return m?m[1]:'home';}
let current=null, gsapReady=false, lenis=null, stCtx=null;
function viewEl(name){return document.querySelector('.view[data-view="'+name+'"]')||views[0];}

/* —— 按需脚本加载（顺序）。CDN 用国内可达源 + 兜底 —— */
function loadScript(src,timeout=8000){return new Promise((res,rej)=>{const s=document.createElement('script');let done=false;
  const to=setTimeout(()=>{if(done)return;done=true;s.onload=s.onerror=null;s.remove();rej(new Error('timeout '+src));},timeout);
  s.src=src;s.onload=()=>{if(done)return;done=true;clearTimeout(to);res();};
  s.onerror=()=>{if(done)return;done=true;clearTimeout(to);s.remove();rej(new Error('error '+src));};
  document.head.appendChild(s);});}
// 国内优先（npmmirror / bootcdn），失败再退 jsdelivr
function loadFirst(urls){return urls.reduce((p,u)=>p.catch(()=>loadScript(u)),Promise.reject());}
const CDN={
  gsap:['assets/vendor/gsap.min.js','https://registry.npmmirror.com/gsap/3.12.5/files/dist/gsap.min.js','https://cdn.bootcdn.net/ajax/libs/gsap/3.12.5/gsap.min.js','https://cdn.jsdelivr.net/npm/gsap@3.12.5/dist/gsap.min.js'],
  st:['assets/vendor/ScrollTrigger.min.js','https://registry.npmmirror.com/gsap/3.12.5/files/dist/ScrollTrigger.min.js','https://cdn.bootcdn.net/ajax/libs/gsap/3.12.5/ScrollTrigger.min.js','https://cdn.jsdelivr.net/npm/gsap@3.12.5/dist/ScrollTrigger.min.js'],
  lenis:['assets/vendor/lenis.min.js','https://registry.npmmirror.com/lenis/1.1.13/files/dist/lenis.min.js','https://cdn.jsdelivr.net/npm/lenis@1.1.13/dist/lenis.min.js'],
  mermaid:['https://registry.npmmirror.com/mermaid/10.9.1/files/dist/mermaid.min.js','https://cdn.bootcdn.net/ajax/libs/mermaid/10.9.1/mermaid.min.js','https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js'],
  katex:['assets/vendor/katex.min.js','https://registry.npmmirror.com/katex/0.16.9/files/dist/katex.min.js','https://cdn.bootcdn.net/ajax/libs/KaTeX/0.16.9/katex.min.js','https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js']
};
(async function boot(){
  try{
    if(reduceMotion){
      bindNativeScroll();
      gsapReady=false;
      revealSite();
      return;
    }
    await loadFirst(CDN.gsap);
    await loadFirst(CDN.st);
    gsap.registerPlugin(ScrollTrigger);
    // lenis 是可选平滑滚动；它单独失败/挂死不该拖垮整个 GSAP 层（退回原生滚动即可）
    try{
      await loadFirst(CDN.lenis);
      lenis=new Lenis({lerp:0.16,wheelMultiplier:1,smoothWheel:true});
      lenis.on('scroll',()=>{ScrollTrigger.update();onScrollLight();});
      gsap.ticker.add(t=>lenis.raf(t*1000));
      gsap.ticker.lagSmoothing(0);
    }catch(le){ lenis=null; bindNativeScroll(); }
    gsapReady=true;root.classList.add('gsap-on');
    buildScroll(viewEl(current||curHash()));
    // 字体换上后 .pintrack 会变宽：独立于揭幕路径，字体就绪后重测 pin + 刷新 ScrollTrigger
    if(document.fonts&&document.fonts.ready){document.fonts.ready.then(()=>{if(typeof layoutPins==='function'){layoutPins();updatePins();}if(window.ScrollTrigger)ScrollTrigger.refresh();});}
  }catch(e){ bindNativeScroll(); }
  finally{ revealSite(); }
})();

/* ═══ 揭幕：等字体就绪 + 开机动画打完（或硬上限兜底）═══ */
let revealed=false;
let siteReady=false;        // 站点首屏构建完成
function revealSite(){siteReady=true;maybeReveal();}
function maybeReveal(){
  if(revealed)return;
  // 必须满足：站点就绪 + 开机打字打完（让加载动画放完，不中途切）
  if(!(siteReady && window.__bootDone))return;
  revealed=true;
  const boot=document.getElementById('boot');
  const go=()=>{root.classList.remove('booting');if(boot)boot.classList.add('gone');
    if(typeof layoutPins==='function'){layoutPins();updatePins();}
    // 揭幕后再点亮当前视图：开机帘幕期间别让首屏揭示动画在黑幕后白跑（揭幕即静态弹出）
    try{setupReveals(viewEl(current||curHash()));}catch(e){}
    setTimeout(()=>{if(boot&&boot.parentNode)boot.parentNode.removeChild(boot);if(typeof layoutPins==='function'){layoutPins();updatePins();}if(window.ScrollTrigger)ScrollTrigger.refresh();},650);};
  if(document.fonts&&document.fonts.ready){document.fonts.ready.then(()=>requestAnimationFrame(go));}
  else requestAnimationFrame(go);
}
// 轮询打字完成（打字脚本在 head 内联，独立于 site.js）
const _bootPoll=setInterval(()=>{if(window.__bootDone){clearInterval(_bootPoll);maybeReveal();}},80);
// 硬上限：无论打字/CDN 多慢，2.6s 后强制揭幕，绝不永久卡加载（本地 vendor 优先，正常毫秒级就绪）
setTimeout(()=>{ if(!gsapReady){bindNativeScroll();} window.__bootDone=true; clearInterval(_bootPoll); siteReady=true; revealed?0:(revealed=true,(function(){const boot=document.getElementById('boot');root.classList.remove('booting');if(typeof layoutPins==='function'){layoutPins();updatePins();}try{setupReveals(viewEl(current||curHash()));}catch(e){}if(boot){boot.classList.add('gone');setTimeout(()=>{if(boot.parentNode)boot.parentNode.removeChild(boot);if(typeof layoutPins==='function'){layoutPins();updatePins();}if(window.ScrollTrigger)ScrollTrigger.refresh();},650);}})()); },2600);
function bindNativeScroll(){ addEventListener('scroll',onScrollLight,{passive:true}); /* 退化路径用 IO 揭示 */ }
function scrollY_(){return lenis?lenis.scroll:(scrollY||document.documentElement.scrollTop||0);}
function scrollTopNow(){ if(lenis)lenis.scrollTo(0,{immediate:true}); else window.scrollTo(0,0); }

/* —— 轻量滚动副作用：nav 态 + 进度环 + 钉屏横推（与 GSAP 并存）—— */
const progRing=mkProgressRing();
/* —— 回到顶部按钮：滚动超过 420px 才现身（文档页 spec/guide 等长页受益最大）—— */
function mkBackTop(){
  const b=document.createElement('button');b.id='backTop';b.type='button';b.setAttribute('aria-label','回到顶部');
  b.innerHTML='<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path d="M12 5l-7 7h4v7h6v-7h4z" fill="currentColor"/></svg>';
  document.body.appendChild(b);
  b.onclick=()=>{
    if(lenis)lenis.scrollTo(0,{duration:reduceMotion?0:0.8}); else window.scrollTo({top:0,behavior:reduceMotion?'auto':'smooth'}); };
  return {set(on){b.classList.toggle('on',on);}};
}
const backTop=mkBackTop();
function isDocView(){return current==='spec'||current==='guide';}
function updateBackTop(){
  if(backTop)backTop.set(isDocView()&&scrollY_()>420);
}
function onScrollLight(){
  const y=scrollY_();
  if(nav)nav.classList.toggle('scrolled',y>28);
  const max=(document.documentElement.scrollHeight-innerHeight)||1;
  progRing.set(Math.min(Math.max(y/max,0),1),y>120);
  updateBackTop();
  updatePins();
}
// 非 Lenis 兜底：原生滚动也持续刷新钉屏
addEventListener('scroll',()=>{ if(!lenis){updatePins();updateBackTop();} },{passive:true});
let _rz;addEventListener('resize',()=>{clearTimeout(_rz);_rz=setTimeout(()=>{if(typeof layoutPins==='function'){layoutPins();updatePins();}if(window.ScrollTrigger)ScrollTrigger.refresh();},150);});

/* —— split-text —— */
function splitChars(el){
  if(el.dataset.split)return;el.dataset.split='1';
  const txt=el.textContent;el.setAttribute('aria-label',txt);el.classList.add('split-chars');
  el.innerHTML=[...txt].map((c,i)=>{  const d=(Math.min(i*0.014,0.18)).toFixed(3);
    return c===' '?'<span class="ch">&nbsp;</span>':'<span class="ch" style="transition-delay:'+d+'s">'+c+'</span>';}).join('');
}
function wrapLine(el){if(el.dataset.lined)return;el.dataset.lined='1';el.innerHTML='<span class="ln">'+el.innerHTML+'</span>';}
function enhanceSplit(view){
  view.querySelectorAll('.hero h1,.pagehead h1').forEach(h=>{
    if(h.dataset.split||h.dataset.lined)return;
    if(h.querySelector('.elabel,.em')){h.classList.add('reveal-lines');wrapLine(h);}
    else splitChars(h);
  });
}
function autoEnhance(view){
  view.querySelectorAll('.code').forEach(el=>el.classList.add('mask-up'));
  if(reduceMotion)return;
  view.querySelectorAll('.pagehead .label,.hero .label').forEach(el=>{if(!el.hasAttribute('data-parallax'))el.setAttribute('data-parallax','0.035');});
  view.querySelectorAll('.bignum,.mode-badge').forEach(el=>{if(!el.hasAttribute('data-parallax'))el.setAttribute('data-parallax','0.06');});
}

/* ═══ Mermaid 懒加载 + 主题联动渲染 ═══ */
let mermaidLib=null,mermaidLoading=null;
function mermaidVars(){
  const cs=getComputedStyle(document.documentElement),g=n=>cs.getPropertyValue(n).trim();
  const card=g('--card-solid'),acc=g('--accent'),accd=g('--accent-d'),text=g('--text'),bg=g('--bg2'),faint=g('--text-faint');
  return {primaryColor:card,primaryBorderColor:acc,primaryTextColor:text,lineColor:accd,
    secondaryColor:bg,tertiaryColor:bg,clusterBkg:bg,clusterBorder:faint,
    edgeLabelBackground:card,titleColor:text,fontFamily:"'JetBrains Mono','PingFang SC',monospace",fontSize:'13px'};
}
function ensureMermaid(){
  if(mermaidLib)return Promise.resolve(mermaidLib);
  if(mermaidLoading)return mermaidLoading;
  mermaidLoading=loadFirst(CDN.mermaid).then(()=>{mermaidLib=window.mermaid;return mermaidLib;})
    .catch(()=>{root.classList.add('no-mermaid');return null;});
  return mermaidLoading;
}

/* ═══ KaTeX：公式渲染。[data-tex] 内联，.tex-block 居中展示。CSS 走 head 的 link。═══ */
let katexLib=null,katexLoading=null;
function ensureKatex(){
  if(katexLib)return Promise.resolve(katexLib);
  if(katexLoading)return katexLoading;
  katexLoading=loadFirst(CDN.katex).then(()=>{katexLib=window.katex;return katexLib;}).catch(()=>null);
  return katexLoading;
}
async function renderTex(view){
  const nodes=[...view.querySelectorAll('[data-tex]:not([data-tex-done])')];
  if(!nodes.length)return;
  const kx=await ensureKatex();
  if(!kx)return;   // 加载失败：data-tex 元素里已有降级纯文本，保持原样
  for(const n of nodes){
    try{kx.render(n.getAttribute('data-tex'),n,{throwOnError:false,displayMode:n.classList.contains('tex-block'),
      output:'htmlAndMathml'});n.setAttribute('data-tex-done','1');}catch(e){}
  }
  // KaTeX 改了元素高度：重测 pin + 刷新 ScrollTrigger（与 renderMermaid 一致），
  // 否则公式下方的揭示/钉屏触发点全部测偏。
  if(typeof layoutPins==='function'){layoutPins();updatePins();}
  if(window.ScrollTrigger)ScrollTrigger.refresh();
}
/* mermaid 图内标签翻译表（图结构不变，只换引号内的中文标签）*/
const MERMAID_EN={
"你的这句话 + 上下文":"your line + context",
"⚡ Body · SDK 共振场计算核<br/>observe() 出 BodySnapshot 只读快照":"⚡ Body · SDK resonance core<br/>observe() emits a read-only BodySnapshot",
"认知主链 · 三拍":"cognitive chain · 3 beats",
"PERCEPT · 知觉<br/>只读抽信号，并发安全":"PERCEPT<br/>read-only, concurrency-safe",
"DELIBERATE · 审议<br/>热路径，决定怎么回应":"DELIBERATE<br/>hot path, decides the reply",
"EVOLVE · 进化<br/>唯一写相位，集中提交演化":"EVOLVE<br/>only write phase, commits evolution",
"能力 agent · 挂在三拍能力槽":"capability agents · in beat slots",
"预测你 + 评价":"predict you + appraise",
"表达驱力/风格":"expression drive / style",
"内感受偏置":"interoceptive bias",
"记忆召回":"memory recall",
"说/不说仲裁":"speak / stay-silent arbitration",
"记忆重固化":"memory reconsolidation",
"领域 agent · 长期状态官能（各自唯一写者）":"domain agents · long-term faculties (sole writers)",
"情绪 · 快慢双 EMA":"affect · fast/slow dual-EMA",
"记忆 · 三层激活":"memory · 3-layer activation",
"话语焦点":"discourse focus",
"对你的后验":"posterior about you",
"连续自我":"continuous self",
"学生编码器":"student encoder",
"措辞策略 · 说/不说/主动 · 回复":"wording · speak/hold/initiate · reply",
"注册到三拍能力槽":"register into beat slots",
"经领域接口只读":"read-only via domain interface",
"写回 情绪漂移 / 人格 append / 记忆重固化":"write back affect drift / persona append / reconsolidation",
"文本 + 时间戳 + 上下文":"text + timestamp + context",
"7 模块 · 并行感知，各自注入信号":"7 modules · parallel sensing, each injects signal",
"M2 · 虚空·伤痕":"M2 · Void·Scar",
"M1 · 门控":"M1 · Gating",
"M3 · 层析":"M3 · Sheaf",
"M5 · 边界":"M5 · Boundary",
"M6 · 表达":"M6 · Expression",
"⚡ 共振场 · 441 通道耦合矩阵 · 迭代收敛<br/>Hebbian 可塑性 · Kuramoto 同步 · Hopfield 吸引子 · 谐波身份核":"⚡ Resonance field · 441-channel coupling · iterative convergence<br/>Hebbian plasticity · Kuramoto sync · Hopfield attractor · harmonic identity core",
"情感状态(8维) · 表达决策(express/hold/withdraw) · 涌现指标 Φ":"affect state (8D) · decision (express/hold/withdraw) · emergence Φ",
"Hebbian 反馈 → 耦合权重":"Hebbian feedback → coupling weights",
"伤疤积累 → 回灌":"scar accumulation → feedback",
};
function mermaidSrc(n){
  let s=n.getAttribute('data-msrc')||'';
  if(getLang()==='en'){
    // 按 key 长度降序替换：长短语先于其子串，避免「记忆重固化」先替换破坏长边标签的匹配
    const keys=Object.keys(MERMAID_EN).sort((a,b)=>b.length-a.length);
    for(const zh of keys){if(s.indexOf(zh)>=0)s=s.split(zh).join(MERMAID_EN[zh]);}
  }
  return s;
}
async function renderMermaid(view){
  const nodes=[...view.querySelectorAll('.mermaid')];
  if(!nodes.length)return;
  const m=await ensureMermaid();
  if(!m){root.classList.add('no-mermaid');return;}
  try{
    m.initialize({startOnLoad:false,theme:'base',themeVariables:mermaidVars(),
      flowchart:{curve:'basis',htmlLabels:true,padding:16,nodeSpacing:34,rankSpacing:46},securityLevel:'loose'});
    for(const n of nodes){n.removeAttribute('data-processed');n.removeAttribute('data-rendered');n.textContent=mermaidSrc(n);}
    await m.run({nodes});
    nodes.forEach(n=>n.setAttribute('data-rendered','1'));
    if(window.ScrollTrigger)ScrollTrigger.refresh();
  }catch(e){root.classList.add('no-mermaid');}
}
function rerenderMermaidForTheme(){
  const v=document.querySelector('.view.active');
  if(v&&mermaidLib&&v.querySelector('.mermaid'))renderMermaid(v);
}

/* ═══ GSAP scroll-scrubbed 编排：只做"绑定滚动进度"的电影化部分。
   普通揭示（.r/.reveal-lines/.split-chars/.mask-up/.bar-fill/计数）一律交给 CSS+IO，
   因为 gsap.from 会把元素钉在 opacity:0，一旦触发器算错位置就永久卡死。═══ */
function buildScroll(view){
  if(reduceMotion)return;
  if(stCtx){try{stCtx.revert();}catch(e){}stCtx=null;}
  if(!gsapReady||!view)return;
  stCtx=gsap.context(()=>{
    const q=s=>gsap.utils.toArray(view.querySelectorAll(s));

    /* hero：滚动推走（scrub）。只对 hero 容器在 hero 区间内做，过了就 kill 不影响下文 */
    const hero=view.querySelector('.hero');
    if(hero){
      const h1=hero.querySelector('h1'),sub=hero.querySelector('.sub'),desc=hero.querySelector('.desc'),
            row=hero.querySelector('.row'),stats=hero.querySelector('.stats'),label=hero.querySelector('.label');
      const tl=gsap.timeline({scrollTrigger:{trigger:hero,start:'top top',end:'bottom top',scrub:0.2}});
      if(h1) tl.to(h1,{yPercent:-12,scale:1.03,opacity:0.35,ease:'none'},0);
      if(label) tl.to(label,{yPercent:-70,opacity:0,ease:'none'},0);
      if(sub) tl.to(sub,{yPercent:-48,opacity:0,ease:'none'},0);
      if(desc) tl.to(desc,{yPercent:-36,opacity:0,ease:'none'},0.02);
      if(row) tl.to(row,{yPercent:-24,opacity:0,ease:'none'},0.04);
      if(stats) tl.to(stats,{yPercent:-14,opacity:0.35,ease:'none'},0.06);
    }

    /* 分层视差（scrub）—— 仅装饰元素，卡了也不影响阅读 */
    q('[data-parallax]').forEach(el=>{const sp=parseFloat(el.dataset.parallax)||.1;
      gsap.to(el,{yPercent:-sp*100,ease:'none',scrollTrigger:{trigger:el.closest('.block,.pagehead,.hero,section')||el,start:'top bottom',end:'bottom top',scrub:true}});});

    /* 横推钉屏由 setupPins 独立驱动（见下），不放这里，确保无 GSAP 也能用 */
  },view);
  // 开机帘幕期间布局被锁、字体未换，别在此时测——交给揭幕后/字体就绪的权威刷新
  if(!root.classList.contains('booting'))ScrollTrigger.refresh();
}
/* ═══ 揭示系统：CSS + IntersectionObserver。与 GSAP 无关，永不卡死。═══ */
const REVEAL_SEL='.r,.reveal-lines,.split-chars,.mask-up';
const io=new IntersectionObserver(es=>es.forEach(e=>{
  if(e.isIntersecting){const el=e.target;el.classList.add('seen');
    if(el.classList.contains('bar-fill'))el.style.width=(el.dataset.w||0)+'%';
    if(el.matches('.hero .stat .v,.statbox .v,.metric .v,[data-count] .v'))av(el);
    io.unobserve(el);}
}),{threshold:.12,rootMargin:'0px 0px -7% 0px'});
function setupReveals(view){
  // 切到本视图：先清掉旧 seen，重新观察；首屏内的立即点亮（IO 对已在视口内的也会回调，这里做双保险）
  view.querySelectorAll(REVEAL_SEL+',.bar-fill,.hero .stat .v,.statbox .v,.metric .v,[data-count] .v').forEach(el=>{
    if(el.matches(REVEAL_SEL))el.classList.remove('seen');
    el.dataset.counted='';
    io.observe(el);
  });
  // 双 rAF 后强制点亮首屏可见的（避免 IO 首帧延迟造成"白着进来"）
  requestAnimationFrame(()=>requestAnimationFrame(()=>{
    view.querySelectorAll(REVEAL_SEL).forEach(el=>{
      const r=el.getBoundingClientRect();
      if(r.top<innerHeight*0.95&&r.bottom>0){el.classList.add('seen');io.unobserve(el);}
    });
    view.querySelectorAll('.bar-fill').forEach(f=>{const r=f.getBoundingClientRect();if(r.top<innerHeight*0.95){f.style.width=(f.dataset.w||0)+'%';io.unobserve(f);}});
    view.querySelectorAll('.hero .stat .v,.statbox .v,.metric .v,[data-count] .v').forEach(v=>{const r=v.getBoundingClientRect();if(r.top<innerHeight*0.95){av(v);io.unobserve(v);}});
  }));
}
// 终极兜底：3.2s 后只点亮「当前视口内」的揭示元素，杜绝白屏。视口外的留给
// IntersectionObserver——滚到才播，绝不在屏外提前判完（否则全站滚动揭示动画失效）。
setTimeout(()=>{
  const vis=el=>{const r=el.getBoundingClientRect();return r.top<innerHeight&&r.bottom>0;};
  document.querySelectorAll(REVEAL_SEL).forEach(el=>{if(vis(el)){el.classList.add('seen');io.unobserve(el);}});
  document.querySelectorAll('.bar-fill').forEach(f=>{if(vis(f)){f.style.width=(f.dataset.w||0)+'%';io.unobserve(f);}});
},3200);

/* ═══ 横推钉屏：CSS sticky + 滚动进度驱动 translateX，不依赖 GSAP ═══ */
let pinScenes=[];
let _pinRO=null;
const DWELL=0.16;
function isWide(){return matchMedia('(min-width:761px)').matches;}
function layoutPins(){
  pinScenes.forEach(s=>{
    if(!isWide()){s.pinh.style.height='';s.track.style.transform='';return;}
    // dist 要让最后一张「编号卡」滑到屏幕中心，而非把轨道右对齐——右对齐会让末卡
    // 停在右缘、永远到不了中心，计数因此卡在 5/6 到不了 7。
    const cards=s.countable.length?s.countable:s.panels;
    const lastEl=cards[cards.length-1];
    s.dist=Math.max(0,lastEl.offsetLeft+lastEl.offsetWidth/2-innerWidth/2);
    s.pinh.style.height=(innerHeight + s.dist + innerHeight*DWELL)+'px';
  });
}
function updatePins(){
  if(!pinScenes.length)return;
  const wide=isWide();
  for(const s of pinScenes){
    if(!wide){s.track.style.transform='';continue;}
    const rect=s.pinh.getBoundingClientRect();
    const scrolled=Math.min(Math.max(-rect.top,0),s.dist + innerHeight*DWELL);
    const moveProg=Math.min(scrolled/(s.dist||1),1);
    s.track.style.transform='translate3d('+(-(Math.min(scrolled,s.dist))).toFixed(1)+'px,0,0)';
    s.panels.forEach(p=>{const r=p.getBoundingClientRect();const d=Math.abs(r.left+r.width/2-innerWidth/2)/innerWidth;
      p.style.opacity=(1-Math.min(d,0.55)).toFixed(2);p.style.transform='scale('+(1-Math.min(d*0.16,0.1)).toFixed(3)+')';});
    // 计数由滚动进度直接驱动（而非取最靠中心的卡）——保证 01..N 全程可达、末卡能到 N，
    // 且末段 dwell 期间稳定停在 N，不会因亚像素抖动闪退。
    if(s.count&&s.countable.length){
      const bi=Math.min(s.countable.length-1,Math.round(moveProg*(s.countable.length-1)));
      s.count.textContent=String(bi+1).padStart(2,'0');
    }
  }
}
function setupPins(view){
  pinScenes=[];
  if(_pinRO){_pinRO.disconnect();_pinRO=null;}
  view.querySelectorAll('.pinh').forEach(pinh=>{
    const track=pinh.querySelector('.pintrack');if(!track)return;
    const panels=[...track.children];if(panels.length<2)return;
    const countable=panels.filter(p=>!p.classList.contains('lead-panel'));
    pinScenes.push({pinh,track,panels,countable,count:pinh.querySelector('.pincount b'),dist:0});
  });
  layoutPins();
  requestAnimationFrame(()=>{layoutPins();updatePins();});
  // 字体换上 / 图片加载会改变轨道宽度：重测 dist，避免末卡到不了中心、计数卡住
  if(window.ResizeObserver&&pinScenes.length){
    _pinRO=new ResizeObserver(()=>{layoutPins();updatePins();});
    pinScenes.forEach(s=>_pinRO.observe(s.track));
  }
}

function activate(name,fromHash){
  const target=viewEl(name);name=target.dataset.view;
  if(name===current&&target.classList.contains('active'))return;
  current=name;
  document.body.setAttribute('data-view',name);   // 供 CSS 区分首页地图态 vs 其它页阅读态
  routebar.classList.add('go');routebar.style.width='72%';
  // 切视图前：只用 context.revert()（它会 kill 自己的触发器并还原内联样式）。
  // 绝不再调 ScrollTrigger.getAll().kill()——那会 kill 而不还原，把元素钉死在动画末态。
  if(stCtx){try{stCtx.revert();}catch(e){}stCtx=null;}
  scrollTopNow();
  views.forEach(v=>v.classList.toggle('active',v===target));
  enhanceSplit(target);autoEnhance(target);
  if(target.querySelector('.mermaid'))renderMermaid(target);
  if(target.querySelector('[data-tex]'))renderTex(target);
  setupReveals(target);                 // 揭示永远跑，不依赖 GSAP
  setupPins(target);                    // 横推钉屏（CSS sticky + 滚动驱动），不依赖 GSAP
  if(gsapReady)requestAnimationFrame(()=>buildScroll(target));  // GSAP 只补滚动绑定层
  document.querySelectorAll('[data-nav]').forEach(a=>a.classList.toggle('cur',a.dataset.nav===name));
  document.querySelectorAll('.spine .node').forEach(n=>n.classList.toggle('active',n.dataset.nav===name));
  setTimeout(()=>{routebar.style.width='100%';routebar.classList.remove('go');setTimeout(()=>routebar.style.width='0',300);},260);
  if(!fromHash){const h='#/'+name;if(location.hash!==h)history.pushState(null,'',h);}
  document.title=(name==='home'?'SYLANNE':({embodiment:'本体',engine:'引擎',sylann:'SYLANN',roadmap:'路线',spec:'SPEC 规范',guide:'开发者指南'}[name]||'')+' · SYLANNE')+' — 情感动力学引擎';
  updateBackTop();
  dispatchEvent(new CustomEvent('sylanne:view',{detail:{name}}));  // 通知模块（如 3D 模型）当前视图
}
document.addEventListener('click',e=>{const a=e.target.closest('[data-nav]');if(a){e.preventDefault();activate(a.dataset.nav,false);return;}
  // 文档页目录/页内锚点（#调用方式 这类非 #/xxx）：拦下来手动滚动，不写 hash、不碰路由
  const anc=e.target.closest('.docbody a[href^="#"]');
  if(anc){const id=decodeURIComponent(anc.getAttribute('href').slice(1));
    const t=id&&document.getElementById(id);
    if(t){e.preventDefault();t.scrollIntoView({behavior:'smooth',block:'start'});}}
});
addEventListener('popstate',()=>activate(curHash(),true));
addEventListener('hashchange',()=>{
  // 文档页目录锚点（#调用方式 这类非 #/xxx 格式）：交给浏览器原生跳转，不当路由处理
  const h=location.hash||'';
  if(h&&!/^#\/[a-z]+$/.test(h))return;
  activate(curHash(),true);
});

function av(el){if(el.dataset.counted)return;el.dataset.counted='1';const m=el.textContent.trim().match(/^([\d.]+)(.*)$/);if(!m)return;const tg=+m[1],sf=m[2],dc=(m[1].split('.')[1]||'').length;if(reduceMotion){el.textContent=tg.toFixed(dc)+sf;return;}let s=null;
  (function st(ts){if(!s)s=ts;const p=Math.min((ts-s)/1000,1),e=1-Math.pow(1-p,3);el.textContent=(tg*e).toFixed(dc)+sf;if(p<1)requestAnimationFrame(st);})(performance.now());}

if(!reduceMotion)document.querySelectorAll('.btn,.name,.node-c').forEach(el=>{
  el.classList.add('mag');
  el.addEventListener('mousemove',ev=>{const r=el.getBoundingClientRect();el.style.transform='translate('+((ev.clientX-r.left-r.width/2)*0.06).toFixed(1)+'px,'+((ev.clientY-r.top-r.height/2)*0.08).toFixed(1)+'px)';});
  el.addEventListener('mouseleave',()=>el.style.transform='');
});

(function cursor(){
  if(!matchMedia('(hover:hover)').matches||reduceMotion)return;
  root.classList.add('cursor-on');
  const dot=document.createElement('div');dot.id='cursor';
  const ring=document.createElement('div');ring.id='cursor-ring';
  document.body.append(dot,ring);
  let rx=innerWidth/2,ry=innerHeight/2,tx=rx,ty=ry;
  addEventListener('mousemove',e=>{tx=e.clientX;ty=e.clientY;dot.style.left=tx+'px';dot.style.top=ty+'px';});
  (function loop(){rx+=(tx-rx)*0.2;ry+=(ty-ry)*0.2;ring.style.left=rx+'px';ring.style.top=ry+'px';requestAnimationFrame(loop);})();
  const hot='a,button,.btn,.name,.node-c,.card,.spine .node,.chip';
  document.addEventListener('mouseover',e=>{if(e.target.closest(hot)){dot.classList.add('hot');ring.classList.add('hot');}});
  document.addEventListener('mouseout',e=>{if(e.target.closest(hot)){dot.classList.remove('hot');ring.classList.remove('hot');}});
})();

function mkProgressRing(){
  const w=document.createElement('div');w.id='scrollprog';
  w.innerHTML='<svg width="46" height="46" viewBox="0 0 46 46"><circle class="track" cx="23" cy="23" r="20"></circle><circle class="bar" cx="23" cy="23" r="20"></circle></svg>';
  document.body.appendChild(w);const bar=w.querySelector('.bar');
  return {set(p,on){w.classList.toggle('on',on);bar.style.strokeDashoffset=(126*(1-p)).toFixed(1);}};
}

applyTheme();
activate(curHash(),true);
if(getLang()==='en')applyLang();   // 若上次选了英文，初次进入即翻译

const cv=document.getElementById('bg');
if(cv){
  const cx=cv.getContext('2d');let W,H,DPR,pts=[];
  const resize=()=>{DPR=Math.min(devicePixelRatio||1,2);W=cv.width=innerWidth*DPR;H=cv.height=innerHeight*DPR;cv.style.width=innerWidth+'px';cv.style.height=innerHeight+'px';};
  resize();addEventListener('resize',resize);
  const N=Math.min(22,Math.floor(innerWidth/64));
  for(let i=0;i<N;i++)pts.push({x:Math.random()*W,y:Math.random()*H,vx:(Math.random()-.5)*.06*DPR,vy:(Math.random()-.5)*.06*DPR});
  const acc='184,138,158';
  (function draw(){
    if(window.__field3d){cv.style.display='none';return;}  // 3D 接管后停掉 2D，省 CPU
    if(document.hidden){setTimeout(draw,400);return;}  // 标签页隐藏时停画，省 CPU
    cx.clearRect(0,0,W,H);
    for(const p of pts){p.x+=p.vx;p.y+=p.vy;if(p.x<0||p.x>W)p.vx*=-1;if(p.y<0||p.y>H)p.vy*=-1;}
    for(let i=0;i<pts.length;i++)for(let j=i+1;j<pts.length;j++){const a=pts[i],b=pts[j],d=Math.hypot(a.x-b.x,a.y-b.y),mx=180*DPR;
      if(d<mx){cx.strokeStyle='rgba('+acc+','+(.10*(1-d/mx)).toFixed(3)+')';cx.lineWidth=DPR;cx.beginPath();cx.moveTo(a.x,a.y);cx.lineTo(b.x,b.y);cx.stroke();}}
    for(const p of pts){cx.fillStyle='rgba('+acc+',.35)';cx.beginPath();cx.arc(p.x,p.y,1.4*DPR,0,6.3);cx.fill();}
    requestAnimationFrame(draw);
  })();
}
