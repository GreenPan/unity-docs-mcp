# Unity Docs MCP Server

让 Claude 直接访问 Unity 文档 —— **完全离线**，读取你通过 Unity Hub 安装的本地编辑器自带的文档。

> **关于本项目**：本项目是早期在线抓取版 `unity-docs-mcp` 的分支。我们删除了在线查询功能，重写为本地构建离线数据库进行查询 —— 服务器只读取已安装编辑器自带的文档，完全不发起任何网络请求。

**⚠️ 免责声明**：这是非官方社区项目，与 Unity Technologies 无任何关联，也不代表其立场。

> **适用场景**：还在烦恼你的 Agent 在网络或社区中抓取不知道几手的信息吗？是时候让它们检索真正的官方文档了。安装本 MCP 服务器后，你的 AI 助手可以直接读取本机 Unity 编辑器自带的官方离线文档 —— 权威、与你的引擎版本完全一致、且完全离线。

[English README](README.md) · [日本語版 README](README_ja.md)

## 工作原理

MCP 服务器读取 Unity Hub 安装的编辑器自带的离线文档（`.../Editor/Data/Documentation/en/`）。`unity-docs-mcp build` 把文档转换为每个已安装版本的 SQLite FTS5 全文索引（`~/.unity_docs_mcp/db/search_{version}.db`）。MCP 服务器只通过配置里的 env `UNITY_DOCS_VERSION` 提供**一个版本**的文档，并从构建好的数据库恢复文档目录。不发起任何网络请求。

## 安装

```bash
pip install unity-docs-mcp
```

（PyPI 发布后即可用；源码树开发请用 `pip install -e .`，见[开发](#开发)）

### 第一步：构建离线索引

```bash
unity-docs-mcp build --editor-root "C:\Program Files\Unity\Hub\Editor"
```

`build` 扫描 Hub Editor 目录，为每个已安装的 Unity 版本构建（或复用）SQLite FTS5 索引。首次需一两分钟，之后立即复用。加 `--force` 强制重建。**它不碰任何 IDE 配置** —— 服务器需要你手动配置（下一步）。

### 第二步：把服务器手动添加到你的 IDE

MCP 服务器是一个 stdio 命令。把它加到你的工具的 MCP 配置里，用 `UNITY_DOCS_VERSION` 指向你想服务的版本（`build` 已建索引的，可用 `ls ~/.unity_docs_mcp/db/` 查看）：

```json
{
  "mcpServers": {
    "unity-docs": {
      "command": "<path-to-python>",
      "args": ["-m", "unity_docs_mcp.server"],
      "env": { "UNITY_DOCS_VERSION": "6000.5.7f1" }
    }
  }
}
```

`<path-to-python>` 是装有 `unity-docs-mcp` 的 Python 解释器的**绝对路径**（macOS/Linux 用 `which python`，Windows 用 `where python`）。请使用完整绝对路径，避免 "module not found" 错误。

各工具的配置位置：

- **Claude Code** —— 项目根目录下的 `.mcp.json`：
  ```json
  { "mcpServers": { "unity-docs": {
    "command": "<path-to-python>", "args": ["-m", "unity_docs_mcp.server"],
    "env": { "UNITY_DOCS_VERSION": "6000.5.7f1" } } } }
  ```
- **Claude Desktop** —— `%APPDATA%\Claude\claude_desktop_config.json`（Windows）或 `~/Library/Application Support/Claude/claude_desktop_config.json`（macOS），结构同上。
- **Cursor** —— 项目根目录的 `.cursor/mcp.json`（`mcpServers` 键）。
- **VS Code (Copilot)** —— 项目根目录的 `.vscode/mcp.json`（`servers` 键，并加 `"type": "stdio"`）。
- **OpenCode** —— 项目根目录的 `opencode.json`（`mcp` 键，`"type": "local"`，`command` 为数组，用 `environment` 而非 `env`）。
- **Codex** —— `~/.codex/config.toml` 的 `[mcp_servers.unity-docs]` 表。

编辑配置后重启对应 AI 工具。

> **注意**：不运行 `build` 时，服务器仍可用 —— 首次查询时延迟构建索引（首次可能需几分钟，进度输出到 stderr）。先运行 `build` 只是提前建好。

### 切换 Unity 版本 / 安装目录

```bash
unity-docs-mcp build --editor-root "D:\NewUnity\Hub\Editor" --force
```

然后更新各工具配置里的 `UNITY_DOCS_VERSION` 为你想服务的版本。

## 使用

向 Claude 询问 Unity API：
- "Tell me about GameObject"
- "How do I use NavMeshAgent?"
- "Search for transform methods"

所有查询都解析到你通过 `UNITY_DOCS_VERSION` 指向的**那一个版本**。

## 功能特性

- 🚫 **完全离线** —— 读取本地 Unity 文档，无网络请求
- 🔍 **全文搜索** —— FTS5 索引覆盖页面正文（ScriptReference API + Manual 手册）
- 📖 **手册查询** —— `get_unity_manual_doc` 读取 Unity 手册页面或搜索手册
- 🎯 **只服务单一版本** —— env `UNITY_DOCS_VERSION` 决定服务器读取哪个已建好的版本
- 💾 **持久化索引** —— `build` 为每个版本建 FTS5 DB，重启后复用
- 🛠️ **手动 IDE 配置** —— 每个工具加一条 stdio 条目，无自动配置魔法

## 开发

```bash
git clone https://github.com/Saqoosha/unity-docs-mcp
cd unity-docs-mcp
python -m venv venv
source venv/bin/activate
pip install -e .
python -m unittest discover tests/
```

## 文档

详细文档见 [docs](docs/) 目录。

## 许可证

MIT
