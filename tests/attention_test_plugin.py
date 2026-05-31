"""SylannEngine 群聊注意力测试插件。

所有消息都经过 SylannEngine 计算。
当引擎决定回复时，调用 LLM 生成回复内容，但不投送到群聊。
结果通过 Web 面板查看（http://localhost:9966）。
"""

from __future__ import annotations

import os
import sys
import time
from collections import deque
from pathlib import Path

_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
if _PLUGIN_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_DIR)

from astrbot.api import logger  # noqa: E402
from astrbot.api.event import AstrMessageEvent  # noqa: E402
from astrbot.api.star import Context, Star, register  # noqa: E402

try:
    from sylanne_core import SylanneConfig, SylanneEngine
except ImportError as err:
    raise RuntimeError(
        "缺少前置插件 SylannEngine，请先安装：\nhttps://github.com/Ayleovelle/SylannEngine.git"
    ) from err

DASHBOARD_PORT = 9966
MAX_RECORDS = 500

REPLY_ACTIONS = {"express", "explore", "recover", "reach_out"}


@register(
    "sylann_attention_test",
    "Ayleovelle",
    "SylannEngine 群聊注意力测试 — 计算+生成但不投送",
    "0.1.0",
)
class AttentionTestPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self._context = context
        self._engine: SylanneEngine | None = None
        self._records: deque = deque(maxlen=MAX_RECORDS)
        self._stats = {"total": 0, "triggered": 0}

    async def initialize(self):
        data_dir = Path("./data/sylann_attention_test")
        data_dir.mkdir(parents=True, exist_ok=True)

        self._engine = SylanneEngine(
            data_dir=str(data_dir),
            llm=self._llm_call,
            config=SylanneConfig(diagnostics=True),
        )
        await self._engine.start()
        await self._start_dashboard()
        logger.info("AttentionTest ready — http://localhost:%d", DASHBOARD_PORT)

    async def on_message(self, event: AstrMessageEvent):
        if not self._engine:
            return

        session_id = str(event.unified_msg_origin)
        text = event.message_str
        sender = getattr(event, "nickname", None) or str(getattr(event, "sender_id", "unknown"))

        if not text.strip():
            return

        surface = await self._engine.process(session_id=session_id, text=text)

        d = surface["decision"]
        g = surface["guard"]
        should_reply = d["action"] in REPLY_ACTIONS and g["allowed"]

        reply_text = None
        if should_reply:
            reply_text = await self._generate_reply(text, surface)
            self._stats["triggered"] += 1

        self._stats["total"] += 1

        self._records.append(
            {
                "time": time.strftime("%H:%M:%S"),
                "sender": sender[:10],
                "text": text[:80],
                "action": d["action"],
                "confidence": round(d["confidence"], 3),
                "urgency": round(d["urgency"], 3),
                "warmth": round(surface["state"]["valence"]["warmth"], 3),
                "damage": round(surface["state"]["damage"]["accumulated"], 3),
                "autonomy": round(surface["state"]["boundary"]["autonomy"], 3),
                "guard": "OK" if g["allowed"] else "BLOCKED",
                "risk": round(g["risk_score"], 3),
                "triggered": should_reply,
                "reply": reply_text,
            }
        )

        event.stop_event()

    async def _generate_reply(self, user_text: str, surface: dict) -> str:
        action = surface["decision"]["action"]
        warmth = surface["state"]["valence"]["warmth"]
        _ = surface.get("personality", {}).get("surface", {})

        tone = "温和"
        if warmth > 0.7:
            tone = "热情"
        elif warmth < 0.3:
            tone = "克制"

        system_prompt = (
            f"你是一个有情感的 AI。当前状态：action={action}, warmth={warmth:.2f}, "
            f"tone={tone}。根据状态自然回复，简短即可。"
        )

        try:
            return await self._llm_call(system_prompt, user_text)
        except Exception:
            return "[LLM 调用失败]"

    async def on_shutdown(self):
        if self._engine:
            await self._engine.shutdown()

    async def _start_dashboard(self):
        from aiohttp import web

        app = web.Application()
        app.router.add_get("/", self._page)
        app.router.add_get("/api/records", self._api)
        app.router.add_get("/api/stats", self._api_stats)
        runner = web.AppRunner(app)
        await runner.setup()
        await web.TCPSite(runner, "0.0.0.0", DASHBOARD_PORT).start()

    async def _api(self, request):
        from aiohttp import web

        return web.json_response(list(self._records))

    async def _api_stats(self, request):
        from aiohttp import web

        return web.json_response(self._stats)

    async def _page(self, request):
        from aiohttp import web

        return web.Response(text=HTML, content_type="text/html")

    async def _llm_call(self, system_prompt: str, user_prompt: str) -> str:
        response = await self._context.provider_manager.text_chat(
            prompt=user_prompt,
            system_prompt=system_prompt,
        )
        return response.completion_text


HTML = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>SylannEngine Attention Monitor</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, sans-serif; background: #0d1117; color: #c9d1d9; padding: 20px; }
h1 { font-size: 18px; margin-bottom: 4px; color: #58a6ff; }
.subtitle { color: #8b949e; font-size: 12px; margin-bottom: 16px; }

.layout { display: flex; gap: 20px; }
.chat { flex: 1; max-width: 720px; }
.sidebar { width: 200px; position: sticky; top: 20px; align-self: flex-start; }

.msg { padding: 10px 14px; margin-bottom: 2px; border-radius: 6px; }
.msg:hover { background: #161b22; }
.msg .head { font-size: 12px; color: #8b949e; margin-bottom: 2px; }
.msg .head .sender { color: #c9d1d9; font-weight: 500; }
.msg .body { font-size: 14px; line-height: 1.5; }
.msg .tags { font-size: 11px; color: #484f58; margin-top: 3px; }

.msg.triggered { border-left: 3px solid #3fb950; cursor: pointer; }
.badge { display: inline-block; background: #238636; color: #fff; font-size: 10px; padding: 1px 6px; border-radius: 8px; margin-left: 6px; vertical-align: middle; }

.reply-box { display: none; margin: 2px 0 6px 18px; padding: 10px 14px; background: #1c2128; border-left: 2px solid #58a6ff; border-radius: 4px; }
.reply-box .reply-text { font-size: 13px; line-height: 1.5; }
.reply-box .reply-meta { font-size: 11px; color: #8b949e; margin-top: 4px; }
.reply-box.open { display: block; }

.stats { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 14px; font-size: 12px; }
.stats h3 { font-size: 13px; color: #58a6ff; margin-bottom: 8px; }
.stats .row { display: flex; justify-content: space-between; margin-bottom: 4px; }
.stats .val { color: #c9d1d9; }
.stats .label { color: #8b949e; }
</style>
</head>
<body>
<h1>SylannEngine Attention Monitor</h1>
<p class="subtitle">群聊实时记录 · 绿色 = 引擎决定回复（已生成但未投送） · 点击查看回复</p>

<div class="layout">
<div class="chat" id="chat"></div>
<div class="sidebar">
  <div class="stats" id="stats">
    <h3>Statistics</h3>
    <div class="row"><span class="label">消息总数</span><span class="val" id="s-total">0</span></div>
    <div class="row"><span class="label">触发回复</span><span class="val" id="s-triggered">0</span></div>
    <div class="row"><span class="label">回复率</span><span class="val" id="s-rate">0%</span></div>
  </div>
</div>
</div>

<script>
let lastLen = 0;
async function refresh() {
  try {
    const [recs, stats] = await Promise.all([
      fetch('/api/records').then(r=>r.json()),
      fetch('/api/stats').then(r=>r.json()),
    ]);
    document.getElementById('s-total').textContent = stats.total;
    document.getElementById('s-triggered').textContent = stats.triggered;
    document.getElementById('s-rate').textContent = stats.total ? Math.round(stats.triggered/stats.total*100)+'%' : '0%';

    if (recs.length === lastLen) return;
    lastLen = recs.length;

    const chat = document.getElementById('chat');
    chat.innerHTML = recs.map((m, i) => `
      <div class="msg ${m.triggered ? 'triggered' : ''}" ${m.triggered ? `onclick="toggle(${i})"` : ''}>
        <div class="head"><span class="sender">${m.sender}</span> · ${m.time}</div>
        <div class="body">${m.text}${m.triggered ? '<span class="badge">replied</span>' : ''}</div>
        <div class="tags">${m.action} · conf ${m.confidence} · warmth ${m.warmth} · dmg ${m.damage}${m.triggered ? ' · click to expand' : ''}</div>
      </div>
      ${m.triggered ? `<div class="reply-box" id="reply-${i}">
        <div class="reply-text">${m.reply||'[empty]'}</div>
        <div class="reply-meta">action=${m.action} urgency=${m.urgency} autonomy=${m.autonomy} risk=${m.risk}</div>
      </div>` : ''}
    `).join('');
    chat.scrollTop = chat.scrollHeight;
  } catch(e) {}
}
function toggle(i) { document.getElementById('reply-'+i).classList.toggle('open'); }
refresh();
setInterval(refresh, 2000);
</script>
</body>
</html>"""
