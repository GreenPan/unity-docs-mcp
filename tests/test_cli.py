"""Tests for the unity-docs-mcp CLI (build)."""

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
        self.sandbox_home = os.path.join(self.tmp, "home")
        # Sandbox the user home so the db lands in the sandbox.
        self.env = patch.dict(
            os.environ,
            {
                "USERPROFILE": self.sandbox_home,
                "HOME": self.sandbox_home,
            },
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.tmp)

    def test_build_builds_indexes(self):
        code = main(["build", "--editor-root", self.root])
        self.assertEqual(code, 0)
        db_dir = os.path.join(self.sandbox_home, ".unity_docs_mcp", "db")
        for v in ["6000.5.7f1", "2022.3.45f1"]:
            self.assertTrue(
                os.path.exists(os.path.join(db_dir, f"search_{v}.db")),
                msg=f"expected index db for {v}",
            )

    def test_build_force_rebuild(self):
        self.assertEqual(main(["build", "--editor-root", self.root]), 0)
        self.assertEqual(main(["build", "--editor-root", self.root, "--force"]), 0)
        db_dir = os.path.join(self.sandbox_home, ".unity_docs_mcp", "db")
        self.assertTrue(os.path.exists(os.path.join(db_dir, "search_6000.5.7f1.db")))

    def test_no_valid_editor_root_returns_nonzero(self):
        with patch("unity_docs_mcp.cli._resolve_editor_root", return_value=None):
            code = main(["build"])
        self.assertNotEqual(code, 0)

    def test_build_failure_returns_nonzero(self):
        with patch("unity_docs_mcp.cli._build_indexes", return_value=False), patch(
            "unity_docs_mcp.cli._resolve_editor_root", return_value=self.root
        ):
            code = main(["build", "--editor-root", self.root])
        self.assertNotEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
