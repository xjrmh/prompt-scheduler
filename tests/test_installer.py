import subprocess
import unittest
from unittest.mock import Mock, call, patch

from prompt_scheduler.installer import (
    CODEX_PACKAGE,
    CLAUDE_CODE_PACKAGE,
    ClaudeInstallError,
    install_codex,
    install_claude_code,
    validate_claude_install_prerequisites,
)


class InstallerTests(unittest.TestCase):
    def test_validate_prerequisites_accepts_node_18_plus(self) -> None:
        completed = subprocess.CompletedProcess(
            ["/usr/local/bin/node", "--version"],
            0,
            stdout="v20.11.1\n",
            stderr="",
        )
        with patch(
            "prompt_scheduler.installer.shutil.which",
            side_effect=lambda name: f"/usr/local/bin/{name}",
        ), patch(
            "prompt_scheduler.installer.subprocess.run",
            return_value=completed,
        ):
            self.assertEqual(
                validate_claude_install_prerequisites(),
                ("/usr/local/bin/node", "/usr/local/bin/npm"),
            )

    def test_validate_prerequisites_rejects_old_node(self) -> None:
        completed = subprocess.CompletedProcess(
            ["/usr/local/bin/node", "--version"],
            0,
            stdout="v16.20.0\n",
            stderr="",
        )
        with patch(
            "prompt_scheduler.installer.shutil.which",
            side_effect=lambda name: f"/usr/local/bin/{name}",
        ), patch(
            "prompt_scheduler.installer.subprocess.run",
            return_value=completed,
        ):
            with self.assertRaises(ClaudeInstallError):
                validate_claude_install_prerequisites()

    def test_install_uses_official_npm_package(self) -> None:
        calls = [
            subprocess.CompletedProcess(["node", "--version"], 0, stdout="v20.0.0\n"),
            subprocess.CompletedProcess(["npm", "install"], 0),
        ]
        run_mock = Mock(side_effect=calls)
        with patch(
            "prompt_scheduler.installer.shutil.which",
            side_effect=lambda name: f"/usr/local/bin/{name}",
        ), patch("prompt_scheduler.installer.subprocess.run", run_mock):
            install_claude_code()

        self.assertEqual(
            run_mock.mock_calls[-1],
            call(
                ["/usr/local/bin/npm", "install", "-g", CLAUDE_CODE_PACKAGE],
                capture_output=False,
                text=False,
            ),
        )

    def test_install_codex_uses_official_npm_package(self) -> None:
        calls = [
            subprocess.CompletedProcess(["node", "--version"], 0, stdout="v20.0.0\n"),
            subprocess.CompletedProcess(["npm", "install"], 0),
        ]
        run_mock = Mock(side_effect=calls)
        with patch(
            "prompt_scheduler.installer.shutil.which",
            side_effect=lambda name: f"/usr/local/bin/{name}",
        ), patch("prompt_scheduler.installer.subprocess.run", run_mock):
            install_codex()

        self.assertEqual(
            run_mock.mock_calls[-1],
            call(
                ["/usr/local/bin/npm", "install", "-g", CODEX_PACKAGE],
                capture_output=False,
                text=False,
            ),
        )


if __name__ == "__main__":
    unittest.main()
