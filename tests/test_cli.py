"""Tests for the unity-docs-mcp CLI (start / changesource)."""

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from unity_docs_mcp.cli import main
from tests.helpers import make_fake_unity_install


class TestCLIBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root, _created = make_fake_unity_install(
            self.tmp, ["2022.3.45f1", "6000.5.7f1"]
        )
        self.project = os.path.join(self.tmp, "proj")
        self.sandbox_home = os.path.join(self.tmp, "home")
        os.makedirs(self.project)
        # Sandbox APPDATA (for claude-desktop detection) and the user home
        # (so UnitySearchIndex's default db_dir lands in the sandbox).
        self.env = patch.dict(
            os.environ,
            {
                "APPDATA": os.path.join(self.tmp, "noappdata"),
                "USERPROFILE": self.sandbox_home,
                "HOME": self.sandbox_home,
            },
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.tmp)

    def _cli(self, args, force_python):
        with patch("unity_docs_mcp.cli.write_all") as wa, patch(
            "unity_docs_mcp.cli.sys"
        ) as mock_sys:
            mock_sys.executable = force_python
            code = main(args)
            return code, wa.call_args

    def test_start_builds_index_and_writes_configs(self):
        args = [
            "start",
            "--editor-root", self.root,
            "--project-dir", self.project,
            "--tools", "claude-code,cursor",
        ]
        code, call_args = self._cli(args, r"C:\venv\python.exe")
        self.assertEqual(code, 0)
        # write_all called with the editor root and selected tools.
        self.assertIsNotNone(call_args)
        pos, kwargs = call_args
        self.assertEqual(pos[0], self.root)
        self.assertEqual(kwargs["tools"], ["claude-code", "cursor"])
        self.assertEqual(kwargs["project_dir"], self.project)
        # The db files were actually created under the sandbox home.
        db_dir = os.path.join(self.sandbox_home, ".unity_docs_mcp", "db")
        for v in ["6000.5.7f1", "2022.3.45f1"]:
            self.assertTrue(
                os.path.exists(os.path.join(db_dir, f"search_{v}.db")),
                msg=f"expected index db for {v}",
            )

    def test_changesource_rebuilds_and_refreshes(self):
        # First point the configs at root A, then switch to root B.
        other = os.path.join(self.tmp, "other_root")
        make_fake_unity_install(other, ["6000.5.7f1"])
        args = [
            "changesource",
            "--editor-root", other,
            "--project-dir", self.project,
            "--tools", "claude-code",
        ]
        code, call_args = self._cli(args, r"C:\venv\python.exe")
        self.assertEqual(code, 0)
        self.assertIsNotNone(call_args)
        pos, _kwargs = call_args
        self.assertEqual(pos[0], other)

    def test_no_valid_editor_root_returns_nonzero(self):
        with patch("unity_docs_mcp.cli._resolve_editor_root", return_value=None):
            code = main(["start", "--project-dir", self.project])
        self.assertNotEqual(code, 0)

    def test_build_failure_returns_nonzero(self):
        with patch("unity_docs_mcp.cli._build_indexes", return_value=False), patch(
            "unity_docs_mcp.cli._resolve_editor_root", return_value=self.root
        ):
            code = main(["start", "--project-dir", self.project])
        self.assertNotEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
