# Unity Docs MCP Server

让 Claude 直接访问 Unity 文档 —— **完全离线**，读取你通过 Unity Hub 安装的本地编辑器自带的文档。

> **关于本项目**：本项目是早期在线抓取版 `unity-docs-mcp` 的分支。我们删除了在线查询功能，重写为本地构建离线数据库进行查询 —— 服务器只读取已安装编辑器自带的文档，完全不发起任何网络请求。

**⚠️ 免责声明**：这是非官方社区项目，与 Unity Technologies 无任何关联，也不代表其立场。

[English README](README.md) · [日本語版 README](README_ja.md)

## 工作原理

MCP 服务器读取 Unity Hub 安装的每个编辑器自带的离线文档（`.../Editor/Data/Documentation/en/`）。不发起任何网络请求。每个已安装版本构建一次 SQLite FTS5 全文索引，可在 42,000+ 个脚本参考页面中进行快速的全文搜索。

## 安装

```bash
pip install -e .
```

### 第一步：启动（建库 + 配置 AI 工具）

```bash
unity-docs-mcp start
```

`start` 分两步：

1. **定位文档** —— 它会提示你输入 Unity Hub 的 Editor 目录（例如 `C:\Program Files\Unity\Hub\Editor`），也可以直接传入：
   ```bash
   unity-docs-mcp start --editor-root "C:\Program Files\Unity\Hub\Editor"
   ```
2. **构建搜索索引** —— 为每个已安装的 Unity 版本构建 SQLite FTS5 索引（首次需一两分钟，之后立即复用）。
3. **写入 MCP 配置** —— 把服务器条目写入下方各 AI 工具的配置文件。

### 手动配置（不运行 `start`）

如果你不想运行 `start`，而想手动配置 MCP 客户端，直接把服务器条目加到工具的配置文件即可。服务器命令始终相同：

```json
{
  "mcpServers": {
    "unity-docs": {
      "command": "<path-to-python>",
      "args": ["-m", "unity_docs_mcp.server"],
      "env": { "UNITY_HUB_EDITOR_DIR": "<Unity Hub Editor 目录>" }
    }
  }
}
```

其中：
- `<path-to-python>` 是装有 `unity-docs-mcp` 的 Python 解释器（macOS/Linux 用 `which python` 查找，Windows 用 `where python`）。请使用完整绝对路径，避免 "module not found" 错误。
- `<Unity Hub Editor 目录>` 是已安装编辑器文件夹的父目录，例如 `C:\Program Files\Unity\Hub\Editor`。也可以不写 `env` 块，改用环境变量 `UNITY_HUB_EDITOR_DIR` 指定。

然后放入你的客户端：

**Claude Code** —— 项目根目录下的 `.mcp.json`（顶层键 `mcpServers`）：
```json
{ "mcpServers": { "unity-docs": {
  "command": "<path-to-python>", "args": ["-m", "unity_docs_mcp.server"],
  "env": { "UNITY_HUB_EDITOR_DIR": "C:\\Program Files\\Unity\\Hub\\Editor" } } } }
```

**Claude Desktop** —— `%APPDATA%\Claude\claude_desktop_config.json`（Windows）或
`~/Library/Application Support/Claude/claude_desktop_config.json`（macOS），结构同上。

> **注意**：不运行 `start` 时，搜索索引会在**首次查询时延迟构建**（首次可能需几分钟，进度输出到 stderr）。先运行 `start` 会提前建好索引，并自动写入 Cursor、VS Code (Copilot)、OpenCode、Codex 的配置 —— 具体文件路径见 [docs/DETAILED_GUIDE.md](docs/DETAILED_GUIDE.md)。

### 切换 Unity 安装目录

如果换到不同的编辑器目录（新安装、换了盘符）：

```bash
unity-docs-mcp changesource --editor-root "D:\NewUnity\Hub\Editor"
```

`changesource` 会从新目录重建索引，并刷新所有工具配置。

### 支持的 AI 工具

`start` 会为以下工具写入 MCP 配置：**Claude Desktop**、**Claude Code**（`.mcp.json`）、**Cursor**、**VS Code (Copilot)**、**OpenCode**、**Codex**。

用 `--tools` 选择子集：

```bash
unity-docs-mcp start --tools claude-desktop,claude-code
```

可选工具名：`claude-desktop`, `claude-code`, `cursor`, `vscode`, `opencode`, `codex`。

## 使用

向 Claude 询问 Unity API：
- "Tell me about GameObject"
- "How do I use NavMeshAgent?"
- "Search for transform methods"

所有查询都会解析到你**已安装的 Unity 版本**。请求的版本未安装时，会回退到最新已安装版本并附加说明（例如 `6000.0 not installed; using 6000.5.7f1`）。

## 功能特性

- 🚫 **完全离线** —— 读取本地 Unity 文档，无网络请求
- 🔍 **全文搜索** —— FTS5 索引覆盖页面正文（ScriptReference API + Manual 手册）
- 📖 **手册查询** —— `get_unity_manual_doc` 读取 Unity 手册页面或搜索手册
- 🎯 **精确匹配已安装版本** —— 前缀匹配将 `6000.5` 解析为 `6000.5.7f1`；未安装版本回退到最新已安装并注明
- 💾 **持久化索引** —— 每个版本构建一次，重启后复用
- ⚙️ **一键设置** —— `start` 构建索引并接入全部 6 种 AI 工具

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
