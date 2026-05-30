<!-- markdownlint-disable MD033 -->
<!-- markdownlint-disable MD041 -->

![SylannEngine](https://socialify.git.ci/Ayleovelle/SylannEngine/image?custom_description=Affective+Computation+Engine+SDK+for+AstrBot&description=1&font=Inter&forks=1&issues=1&language=1&name=1&owner=1&pattern=Brick+Wall&pulls=1&stargazers=1&theme=Auto)

<p align="center">
  <img src="https://img.shields.io/badge/License-AGPL_3.0-blue.svg" alt="License: AGPL-3.0">
  <img src="https://img.shields.io/badge/Python-3.10+-blue.svg" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/AstrBot-v4.11.2+-orange.svg" alt="AstrBot v4.11.2+">
  <img src="https://img.shields.io/badge/Status-Preview-yellow.svg" alt="Status: Preview">
</p>

<p align="center">
  <a href="SPEC.md"><strong>📐 标准规范</strong></a> ·
  <a href="AGENT_GUIDE.md"><strong>🤖 开发者指南</strong></a> ·
  <a href="CHANGELOG.md"><strong>📋 更新日志</strong></a>
</p>

---

> **这是 `plugin` 分支** — 将 SylannEngine 包装为 AstrBot 插件，安装一次即可供所有其他插件共享使用。
>
> 如果你是 SDK 开发者，请切换到 [`main` 分支](https://github.com/Ayleovelle/SylannEngine/tree/main)。

## 为什么需要这个分支

如果多个插件作者都把 `sylanne_core/` 复制到自己的插件里，会导致：
- 同一个 AstrBot 实例里存在多份 SylannEngine 代码
- 版本不一致，状态互相隔离
- 更新困难，每个插件都要单独更新

**解决方案**：安装这个插件分支，所有其他插件直接 `from sylanne_core import SylanneEngine` 即可。

## 安装

在 AstrBot WebUI 的插件页面，选择「从 Git 仓库安装」，输入：

```
https://github.com/Ayleovelle/SylannEngine.git -b plugin
```

## 其他插件如何使用

安装本插件后，你的插件代码里直接 import：

```python
from sylanne_core import SylanneEngine, SylanneConfig

class MyPlugin(Star):
    async def initialize(self):
        self._engine = SylanneEngine(
            data_dir="./data/sylannengine",
            llm=self._llm_call,
            config=SylanneConfig(),
        )
        await self._engine.start()

    async def on_message(self, event):
        surface = await self._engine.process(
            session_id=event.user_id,
            text=event.message_str,
        )
        # 使用 surface 调整你的回复...
```

不需要复制任何文件，不需要 git submodule。

## 注意

- 本插件不处理消息、不注册命令、不注入 prompt
- 它只做一件事：确保 `sylanne_core` 在 Python 路径中可用
- 完整 API 文档见 [开发者指南](AGENT_GUIDE.md) 和 [标准规范](SPEC.md)

---

## 许可证

GNU Affero General Public License v3.0 - 详见 [LICENSE](LICENSE) 文件。
