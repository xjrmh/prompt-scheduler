import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from prompt_scheduler.providers import find_provider_executable


class ProviderTests(unittest.TestCase):
    def test_find_provider_executable_uses_env_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            executable = Path(tmp) / "codex"
            executable.write_text("#!/bin/sh\n", encoding="utf-8")
            executable.chmod(0o755)

            with patch.dict(
                "os.environ",
                {"PROMPT_SCHEDULER_CODEX_BIN": str(executable)},
                clear=False,
            ), patch("prompt_scheduler.providers.shutil.which", return_value=None):
                self.assertEqual(find_provider_executable("codex"), str(executable))


if __name__ == "__main__":
    unittest.main()
