from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from claude_session_scheduler.auth import check_claude_auth, looks_like_auth_required


def write_fake_claude(directory: Path, body: str) -> Path:
    executable = directory / "claude"
    executable.write_text("#!/bin/sh\n" + body + "\n", encoding="utf-8")
    executable.chmod(0o755)
    return executable


class AuthTests(unittest.TestCase):
    def test_check_claude_auth_logged_in(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake = write_fake_claude(
                Path(tmp),
                "echo '{\"loggedIn\":true,\"authMethod\":\"claude.ai\"}'",
            )

            result = check_claude_auth(str(fake))

            self.assertTrue(result.authenticated)
            self.assertEqual(result.auth_method, "claude.ai")
            self.assertIsNone(result.error)

    def test_check_claude_auth_logged_out(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake = write_fake_claude(Path(tmp), "echo '{\"loggedIn\":false}'")

            result = check_claude_auth(str(fake))

            self.assertFalse(result.authenticated)
            self.assertIn("claude auth login", result.error or "")

    def test_looks_like_auth_required(self) -> None:
        self.assertTrue(looks_like_auth_required("Please log in with claude auth login."))
        self.assertFalse(looks_like_auth_required("Claude usage limit reached."))


if __name__ == "__main__":
    unittest.main()
