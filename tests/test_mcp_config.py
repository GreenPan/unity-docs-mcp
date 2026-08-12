"""Tests for MCP config writing across supported AI tools."""

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from unity_docs_mcp import mcp_config

EDITOR_ROOT = r"C:\Program Files\Unity\Hub\Editor"
PYTHON_EXE = r"C:\venv\Scripts\python.exe"


class TestJSONConfigs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.project = os.path.join(self.tmp, "proj")
        os.makedirs(self.project)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _load(self, path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def test_claude_code_entry(self):
        results = mcp_config.write_all(
            EDITOR_ROOT, python_exe=PYTHON_EXE, project_dir=self.project,
            tools=["claude-code"],
        )
        self.assertEqual(results["claude-code"], "written")
        data = self._load(os.path.join(self.project, ".mcp.json"))
        entry = data["mcpServers"]["unity-docs"]
        self.assertEqual(entry["command"], PYTHON_EXE)
        self.assertEqual(entry["args"], ["-m", "unity_docs_mcp.server"])
        self.assertEqual(entry["env"], {"UNITY_HUB_EDITOR_DIR": EDITOR_ROOT})

    def test_cursor_entry(self):
        mcp_config.write_all(
            EDITOR_ROOT, python_exe=PYTHON_EXE, project_dir=self.project,
            tools=["cursor"],
        )
        data = self._load(os.path.join(self.project, ".cursor", "mcp.json"))
        self.assertIn("unity-docs", data["mcpServers"])

    def test_vscode_entry_has_type_and_cwd(self):
        mcp_config.write_all(
            EDITOR_ROOT, python_exe=PYTHON_EXE, project_dir=self.project,
            tools=["vscode"],
        )
        data = self._load(os.path.join(self.project, ".vscode", "mcp.json"))
        entry = data["servers"]["unity-docs"]
        self.assertEqual(entry["type"], "stdio")
        self.assertEqual(entry["cwd"], self.project)
        self.assertEqual(entry["command"], PYTHON_EXE)

    def test_opencode_entry_array_command(self):
        mcp_config.write_all(
            EDITOR_ROOT, python_exe=PYTHON_EXE, project_dir=self.project,
            tools=["opencode"],
        )
        data = self._load(os.path.join(self.project, "opencode.json"))
        entry = data["mcp"]["unity-docs"]
        self.assertEqual(entry["type"], "local")
        self.assertTrue(entry["enabled"])
        self.assertEqual(
            entry["command"], [PYTHON_EXE, "-m", "unity_docs_mcp.server"]
        )
        self.assertEqual(
            entry["environment"], {"UNITY_HUB_EDITOR_DIR": EDITOR_ROOT}
        )

    def test_claude_desktop_entry(self):
        appdata = os.path.join(self.tmp, "AppData")
        claude_dir = os.path.join(appdata, "Claude")
        os.makedirs(claude_dir)
        with patch.dict(os.environ, {"APPDATA": appdata}):
            results = mcp_config.write_all(
                EDITOR_ROOT, python_exe=PYTHON_EXE, project_dir=self.project,
                tools=["claude-desktop"],
            )
        self.assertEqual(results["claude-desktop"], "written")
        data = self._load(os.path.join(claude_dir, "claude_desktop_config.json"))
        entry = data["mcpServers"]["unity-docs"]
        self.assertEqual(entry["command"], PYTHON_EXE)

    def test_claude_desktop_skipped_when_not_installed(self):
        appdata = os.path.join(self.tmp, "NoAppData")
        os.makedirs(appdata)  # dir exists but no Claude subfolder
        with patch.dict(os.environ, {"APPDATA": appdata}):
            results = mcp_config.write_all(
                EDITOR_ROOT, python_exe=PYTHON_EXE, project_dir=self.project,
                tools=["claude-desktop"],
            )
        self.assertEqual(results["claude-desktop"], "skipped")


class TestCodexToml(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.project = os.path.join(self.tmp, "proj")
        os.makedirs(self.project)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _config_path(self):
        return os.path.join(self.tmp, "config.toml")

    def _call(self, editor_root=EDITOR_ROOT):
        with patch.object(mcp_config, "_tool_path") as tp:
            tp.side_effect = lambda tool, proj: (
                self._config_path() if tool == "codex" else None
            )
            return mcp_config.write_all(
                editor_root, python_exe=PYTHON_EXE, project_dir=self.project,
                tools=["codex"],
            )

    def test_writes_block(self):
        results = self._call()
        self.assertEqual(results["codex"], "written")
        with open(self._config_path(), encoding="utf-8") as f:
            text = f.read()
        self.assertIn("[mcp_servers.unity-docs]", text)
        self.assertIn('command = "{}"'.format(PYTHON_EXE.replace("\\", "\\\\")), text)
        self.assertIn('args = ["-m", "unity_docs_mcp.server"]', text)
        self.assertIn(
            'env = {{ UNITY_HUB_EDITOR_DIR = "{}" }}'.format(
                EDITOR_ROOT.replace("\\", "\\\\")
            ),
            text,
        )
        self.assertIn('type = "stdio"', text)
        self.assertIn('cwd = "{}"'.format(self.project.replace("\\", "\\\\")), text)

    def test_preserves_existing_tables(self):
        pre = (
            "# my comment\n"
            '[mcp_servers.other]\n'
            'command = "echo"\n'
            'args = ["hi"]\n'
        )
        with open(self._config_path(), "w", encoding="utf-8") as f:
            f.write(pre)
        results = self._call()
        self.assertEqual(results["codex"], "written")
        with open(self._config_path(), encoding="utf-8") as f:
            text = f.read()
        self.assertIn("[mcp_servers.other]", text)
        self.assertIn('command = "echo"', text)
        self.assertIn("[mcp_servers.unity-docs]", text)

    def test_updates_existing_block_changesource(self):
        pre = (
            '[mcp_servers.unity-docs]\n'
            'command = "OLD"\n'
            'args = ["-m", "unity_docs_mcp.server"]\n'
            'cwd = "OLD"\n'
            'env = { UNITY_HUB_EDITOR_DIR = "OLD" }\n'
        )
        with open(self._config_path(), "w", encoding="utf-8") as f:
            f.write(pre)
        new_root = r"D:\NewEditor"
        results = self._call(editor_root=new_root)
        self.assertEqual(results["codex"], "written")
        with open(self._config_path(), encoding="utf-8") as f:
            text = f.read()
        self.assertNotIn("OLD", text)
        self.assertIn(
            'env = {{ UNITY_HUB_EDITOR_DIR = "{}" }}'.format(
                new_root.replace("\\", "\\\\")
            ),
            text,
        )

    def test_backup_created(self):
        pre = '[mcp_servers.other]\ncommand = "echo"\n'
        with open(self._config_path(), "w", encoding="utf-8") as f:
            f.write(pre)
        self._call()
        self.assertTrue(os.path.exists(self._config_path() + ".bak"))


class TestMergeAndBackup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.project = os.path.join(self.tmp, "proj")
        os.makedirs(self.project)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_preserves_other_entries(self):
        path = os.path.join(self.project, ".mcp.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"mcpServers": {"other": {"command": "x"}}}, f)
        mcp_config.write_all(
            EDITOR_ROOT, python_exe=PYTHON_EXE, project_dir=self.project,
            tools=["claude-code"],
        )
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertIn("other", data["mcpServers"])
        self.assertIn("unity-docs", data["mcpServers"])

    def test_bak_created_on_change(self):
        path = os.path.join(self.project, ".mcp.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"mcpServers": {}}, f)
        mcp_config.write_all(
            EDITOR_ROOT, python_exe=PYTHON_EXE, project_dir=self.project,
            tools=["claude-code"],
        )
        self.assertTrue(os.path.exists(path + ".bak"))

    def test_skipped_when_already_current(self):
        results = mcp_config.write_all(
            EDITOR_ROOT, python_exe=PYTHON_EXE, project_dir=self.project,
            tools=["claude-code"],
        )
        self.assertEqual(results["claude-code"], "written")
        results2 = mcp_config.write_all(
            EDITOR_ROOT, python_exe=PYTHON_EXE, project_dir=self.project,
            tools=["claude-code"],
        )
        self.assertEqual(results2["claude-code"], "skipped")

    def test_changesource_updates_env(self):
        path = os.path.join(self.project, ".mcp.json")
        mcp_config.write_all(
            EDITOR_ROOT, python_exe=PYTHON_EXE, project_dir=self.project,
            tools=["claude-code"],
        )
        new_root = r"D:\NewEditor"
        mcp_config.write_all(
            new_root, python_exe=PYTHON_EXE, project_dir=self.project,
            tools=["claude-code"],
        )
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(
            data["mcpServers"]["unity-docs"]["env"]["UNITY_HUB_EDITOR_DIR"],
            new_root,
        )

    def test_unknown_tool_error(self):
        results = mcp_config.write_all(
            EDITOR_ROOT, python_exe=PYTHON_EXE, project_dir=self.project,
            tools=["not-a-tool"],
        )
        self.assertEqual(results["not-a-tool"], "error")

    def test_default_python_and_project(self):
        results = mcp_config.write_all(EDITOR_ROOT, project_dir=self.project)
        with open(os.path.join(self.project, ".mcp.json"), encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(
            data["mcpServers"]["unity-docs"]["command"], sys.executable
        )


if __name__ == "__main__":
    unittest.main()
