# SYLANNE 官网 · 部署说明（2c2g 静态站）

整站是**纯静态**：`index.html` + `styles.css` + `site.js`（+ 可选 `ambient.mp3`）。
没有后端、没有数据库、没有构建步骤。服务器只负责发这几个文件，其余（字体、GSAP、Lenis、Mermaid）全走国内 CDN，不占你带宽。

## 文件清单
- `index.html`  — 单页应用（5 个视图：首页 / 本体 / 引擎 / SYLANN / 路线）
- `styles.css`  — 全部样式
- `site.js`     — 路由 + 动效 + 播放器 + Mermaid 懒加载
- `ambient.mp3` — 可选，环境音；不放也不报错（播放器安静失败）

## 直接用法
丢进任意静态服务器的网站根目录即可。本地双击 `index.html` 也能跑。

## nginx 配置（gzip + 长缓存，2c2g 省带宽关键）
```nginx
server {
    listen 80;
    server_name your.domain;
    root /var/www/sylanne;        # 放上面几个文件的目录
    index index.html;

    # gzip：HTML/CSS/JS 压缩后体积砍掉 60-75%
    gzip on;
    gzip_comp_level 6;
    gzip_min_length 1024;
    gzip_types text/html text/css application/javascript application/json image/svg+xml;
    gzip_vary on;

    # 静态资源长缓存（带 hash 的可设更长；这里按文件类型）
    location ~* \.(css|js)$   { expires 7d;  add_header Cache-Control "public"; }
    location ~* \.(mp3|woff2|woff|ttf|png|jpg|svg|ico)$ { expires 30d; add_header Cache-Control "public"; }
    location = /index.html    { expires -1;  add_header Cache-Control "no-cache"; }

    # SPA 用 hash 路由（#/engine），不需要 try_files 重写；直接发 index 即可
    location / { try_files $uri $uri/ /index.html; }
}
```
有条件开 brotli 比 gzip 再省一档（需 `ngx_brotli` 模块）。

## 为什么这样最省 2c2g
- 第三方库（约 1MB+ 的 GSAP/Lenis/Mermaid）走 CDN，你的服务器一个字节都不发。
- 中文字体用系统字体，省掉几 MB webfont 下载。
- gzip 后，你服务器实际只发约 40-50 KB 文本，首屏后浏览器全缓存。
- 背景动画、Mermaid 都是客户端算，不占服务器 CPU。

## 想完全离线 / 不依赖 CDN？
把 `site.js` 顶部 `CDN` 对象里的库下载到本地、改成相对路径，字体也自托管即可。
代价是走你服务器带宽（但都是一次性、可缓存）。当前默认是「国内 CDN 优先」，已是 2c2g 最省的方案。
