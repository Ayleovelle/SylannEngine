#!/usr/bin/env python3
"""
SYLANNE 官网构建脚本
把 src/ 下的模块化源拼装成根目录的扁平静态产物：
  src/partials + src/views   -> index.html
  src/css/*.css (按名排序)    -> styles.css
  src/i18n/*.json (合并)      -> i18n.js  (window.I18N = {...})
  仓库根 SPEC.md / AGENT_GUIDE.md -> 站内文档视图(#/spec #/guide)
site.js 不经过构建，手写单文件直接用。
用法：python build.py
"""
import glob
import html as _html
import json
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC  = os.path.join(ROOT, 'src')
REPO = os.path.dirname(ROOT)   # 仓库根（SPEC.md / AGENT_GUIDE.md 在这）

def read(p):
    with open(p, encoding='utf-8') as f: return f.read()

def write(p, s):
    with open(p, 'w', encoding='utf-8') as f: f.write(s)

# ---- 文档页：仓库根 Markdown -> 站内阅读视图 ----
# 每项：视图名 / 源文件 / 面包屑 / 英文小标签 / H1(可含<span class="em">) / 副标
DOC_PAGES = [
    {'name':'spec',  'src':'SPEC.md',
     'crumb':'SPEC 标准规范', 'label':'SDK Specification · sylanne.engine.v1',
     'h1':'SPEC<span class="em"> 规范</span>', 'tagline':'接口协议 · 输入输出契约 · 生命周期'},
    {'name':'guide', 'src':'AGENT_GUIDE.md',
     'crumb':'开发者指南', 'label':'Agent Integration Guide',
     'h1':'开发者<span class="em">指南</span>', 'tagline':'功能模块 · 字段含义 · 集成方法'},
]

def _mermaid_html(src):
    # 套站点 mermaid 容器；源放进 data-msrc（site.js 的 renderMermaid 读它）
    esc = _html.escape(src.strip(), quote=True)
    return ('<div class="mermaid-wrap"><pre class="mermaid" data-msrc="' + esc +
            '"></pre></div>')

def _gh_slug(value, separator):
    # GitHub 兼容锚点：小写、去标点（保留中文/单词字符/连字符）、空格→分隔符。
    # 与文档作者手写 TOC 锚点（如 #1-调用方式 / #3-情感状态--8-子系统-state）对齐，
    # 否则 Python-markdown 默认 slugify 会把中文 ascii-ignore 扔掉导致锚点全失效。
    value = value.strip().lower()
    value = re.sub(r'[^\w \-一-鿿]', '', value, flags=re.U)  # 去标点/破折号
    return value.replace(' ', separator)                            # 不折叠多空格

# 站内文档路由（src 文件名 -> #/路由），其余仓库内 .md 链接回退到 GitHub blob。
# 否则部署成纯静态站后，文内的相对 .md 交叉链接（如 SPEC 里指向 AGENT_GUIDE.md /
# docs/theoretical_spec.md）会 404。
_IN_SITE_DOC = {p['src']: '#/' + p['name'] for p in DOC_PAGES}
_GH_BLOB = 'https://github.com/Ayleovelle/SylannEngine/blob/main/'

def _rewrite_doc_links(html):
    # 仅改写相对 .md 链接；http(s)、#锚点、绝对路径不动。
    def repl(m):
        href = m.group(1)
        if re.match(r'(https?:|#|/|mailto:)', href):
            return m.group(0)
        path, _, frag = href.partition('#')
        path = re.sub(r'^\./', '', path)
        if not path.endswith('.md'):
            return m.group(0)
        if path in _IN_SITE_DOC:                       # 站内已嵌 -> 走 SPA 路由
            return 'href="%s"' % _IN_SITE_DOC[path]
        url = _GH_BLOB + path + (('#' + frag) if frag else '')  # 站外 -> GitHub
        return 'href="%s" target="_blank" rel="noopener"' % url
    return re.sub(r'href="([^"]+)"', repl, html)

def md_to_html(md):
    import markdown
    # 1. 先抽出 ```mermaid 块，换占位符，避开 fenced_code 把它当普通代码
    blocks = []
    def _grab(m):
        blocks.append(m.group(1))
        return '\n\nMERMAIDBLOCK%d\n\n' % (len(blocks) - 1)
    md = re.sub(r'```mermaid\n(.*?)```', _grab, md, flags=re.S)
    # 2. 标准转换：代码围栏 + 表格 + 目录锚点(toc 用 GitHub slugify，匹配文内 #锚点)
    html = markdown.markdown(md, output_format='html5',
                             extensions=['fenced_code', 'tables', 'toc'],
                             extension_configs={'toc': {'slugify': _gh_slug}})
    # 3. 表格套横向滚动容器（窄屏不撑破布局）
    html = re.sub(r'(<table>.*?</table>)', r'<div class="table-wrap">\1</div>',
                  html, flags=re.S)
    # 3.5 目录（紧跟「目录」标题的首个 ul）套 .doc-toc 卡片样式，链接更像可点的入口
    html = re.sub(r'(<h2[^>]*>\s*目录\s*</h2>\s*)<ul>',
                  r'\1<ul class="doc-toc">', html, count=1, flags=re.S)
    # 3.6 改写相对 .md 交叉链接，避免部署后 404
    html = _rewrite_doc_links(html)
    # 4. 回填 mermaid（占位符可能被包进 <p>）
    for i, src in enumerate(blocks):
        ph = 'MERMAIDBLOCK%d' % i
        html = html.replace('<p>' + ph + '</p>', _mermaid_html(src))
        html = html.replace(ph, _mermaid_html(src))
    return html

def build_doc(page):
    body = md_to_html(read(os.path.join(REPO, page['src'])))
    return (
        '<section class="view" data-view="' + page['name'] + '">\n'
        '  <header class="pagehead">\n'
        '    <div class="crumb"><a data-nav="home" href="#/home">首页</a>'
        '<span class="sep">/</span><span>' + page['crumb'] + '</span></div>\n'
        '    <div class="label">' + page['label'] + '</div>\n'
        '    <h1>' + page['h1'] + '</h1>\n'
        '    <div class="tagline">' + page['tagline'] + '</div>\n'
        '  </header>\n'
        '  <section class="block">\n'
        '    <div class="docbody">\n' + body + '\n    </div>\n'
        '  </section>\n'
        '</section>'
    )

# ---- 1. index.html = head + shell-top + views(顺序) + 文档视图 + shell-bottom ----
VIEW_ORDER = ['home', 'embodiment', 'engine', 'sylann', 'roadmap']
def build_html():
    parts = [read(f'{SRC}/partials/head.html').rstrip('\n'),
             read(f'{SRC}/partials/shell-top.html').rstrip('\n')]
    for v in VIEW_ORDER:
        parts.append(read(f'{SRC}/views/{v}.html').rstrip('\n'))
    for page in DOC_PAGES:                       # 文档视图接在常规视图之后
        parts.append(build_doc(page))
    parts.append(read(f'{SRC}/partials/shell-bottom.html').rstrip('\n'))
    write(f'{ROOT}/index.html', '\n'.join(parts) + '\n')
    return len(VIEW_ORDER), len(DOC_PAGES)

# ---- 2. styles.css = css/*.css 按文件名排序拼接 ----
def build_css():
    files = sorted(glob.glob(f'{SRC}/css/*.css'))
    out = []
    for p in files:
        out.append(f'/* ===== {os.path.basename(p)} ===== */')
        out.append(read(p).rstrip('\n'))
    write(f'{ROOT}/styles.css', '\n'.join(out) + '\n')
    return len(files)

# ---- 3. i18n.js = 合并 src/i18n/*.json -> window.I18N ----
def build_i18n():
    merged = {}
    # home 优先，frag 最后兜底；同 key 先到先得
    order = ['home','embodiment','engine','sylann','roadmap','frag']
    for name in order:
        p = f'{SRC}/i18n/{name}.json'
        if not os.path.exists(p): continue
        d = json.loads(read(p))
        for k, v in d.items():
            if k == '__FRAGEND__': continue   # 占位符，跳过
            nk = ' '.join(k.split())           # 空白归一化，与 site.js 运行时一致
            if nk not in merged: merged[nk] = v
    js = ('/* 自动生成，请勿手改；改 src/i18n/*.json 后跑 python build.py */\n'
          'window.I18N=' + json.dumps(merged, ensure_ascii=False, indent=0) + ';\n')
    write(f'{ROOT}/i18n.js', js)
    return len(merged)

if __name__ == '__main__':
    nv, nd = build_html()
    nc = build_css()
    ni = build_i18n()
    print(f'[build] index.html  <- head + shell + {nv} views + {nd} doc pages')
    print(f'[build] styles.css  <- {nc} css modules')
    print(f'[build] i18n.js     <- {ni} translation keys')
    print('[build] site.js     (手写，未参与构建)')
    print('[build] done.')
