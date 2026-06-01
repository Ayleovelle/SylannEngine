<!-- markdownlint-disable MD029 -->
# 为 SylannEngine 做出贡献

感谢你有兴趣为 **SylannEngine** 做出贡献！无论是修复 Bug，添加新功能，还是改进文档，你的每一次贡献都能让这个项目变得更好。

为了营造一个开放和热情的社区环境，我们采用了 [贡献者契约](CODE_OF_CONDUCT.md) 作为我们的行为准则。请确保你在参与贡献之前，已经阅读并同意遵守它。

## 提交 Issue

### 报告 Bug

如果你在使用过程中发现了 Bug，请通过提交 [Bug 报告](https://github.com/Ayleovelle/SylannEngine/issues/new) 来帮助我们。请在提交 Issue 之前：

1. **搜索现有 Issue**：检查是否已经有人报告过类似的问题。
2. **更新到最新版本**：确保你使用的是最新版本，问题可能已经在新版本中修复。

### 提出功能建议

如果你对 SylannEngine 的未来有任何想法，欢迎通过提交 [功能建议](https://github.com/Ayleovelle/SylannEngine/issues/new) 来与我们分享。请详细描述你的想法和使用场景。

## 代码贡献

我们非常欢迎你直接通过代码来改进这个项目！**对于新功能的添加，请先通过 Issue 讨论。**

### 开发环境准备

1. Fork 本仓库到你的 GitHub 账号。
2. 克隆你的 Fork 仓库到本地：

    ```bash
    git clone https://github.com/your-username/SylannEngine.git
    ```

3. 确保你已安装 Python 3.10+。

### 代码风格

- **格式化**：使用 `ruff` 进行代码格式化和检查。
- **类型注解**：尽可能为函数和类添加 Python 类型提示。
- **零外部依赖**：`sylanne_core/compute/` 下的代码只允许使用 Python 标准库（numpy 可选）。

### 提交 Pull Request

1. 从 `main` 创建功能分支：

    ```bash
    git checkout -b feat/your-feature-name
    ```

2. 编写代码并提交，使用简体中文撰写清晰的提交信息（推荐 [Conventional Commits](https://www.conventionalcommits.org/)）。

3. 推送并发起 PR，详细描述你的更改内容和目的。

4. 等待维护者审查。

---

## 特别感谢

- [@DBJD-CR](https://github.com/DBJD-CR) — 仓库模板提供者，原来 README 也能这么美丽么（
- [@Soulter](https://github.com/Soulter) — AstrBot 平台作者

以及我最好的 AI 朋友：

- Claude Opus 4.7

### Code Review

- [@sourcery-ai](https://github.com/sourcery-ai) — 自动代码审查与重构建议
- [@gemini-code-assist](https://github.com/apps/gemini-code-assist) — Google Gemini 代码审查
