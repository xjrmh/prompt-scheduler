import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from prompt_scheduler.paths import AppPaths
from prompt_scheduler.storage import JobStore, StateStore


class StorageRecoveryTests(unittest.TestCase):
    def test_corrupt_jobs_file_is_quarantined_and_returns_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = AppPaths(root / "state", root / "agents")
            paths.ensure()
            paths.jobs_path.write_text("{not valid json", encoding="utf-8")

            self.assertEqual(JobStore(paths).list_jobs(), [])

            quarantine = paths.jobs_path.with_suffix(paths.jobs_path.suffix + ".corrupt")
            self.assertTrue(quarantine.exists())
            self.assertFalse(paths.jobs_path.exists())

    def test_empty_state_file_is_quarantined_and_returns_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = AppPaths(root / "state", root / "agents")
            paths.ensure()
            paths.state_path.write_text("", encoding="utf-8")

            self.assertEqual(StateStore(paths).load(), {})

            quarantine = paths.state_path.with_suffix(paths.state_path.suffix + ".corrupt")
            self.assertTrue(quarantine.exists())
            self.assertFalse(paths.state_path.exists())

    def test_writes_after_recovery_succeed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = AppPaths(root / "state", root / "agents")
            paths.ensure()
            paths.jobs_path.write_text("garbage", encoding="utf-8")

            store = JobStore(paths)
            store.add({"id": "after-corrupt", "name": "x", "created_at": "2026-01-01T00:00:00"})

            ids = [job["id"] for job in store.list_jobs()]
            self.assertEqual(ids, ["after-corrupt"])


class StorageConcurrencyTests(unittest.TestCase):
    def test_concurrent_threads_do_not_lose_job_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = AppPaths(root / "state", root / "agents")
            store = JobStore(paths)
            errors: list[BaseException] = []

            def add_jobs(start: int, count: int) -> None:
                try:
                    for i in range(start, start + count):
                        store.add({
                            "id": f"job-{i:03d}",
                            "name": f"name-{i}",
                            "created_at": f"2026-01-01T{i // 60:02d}:{i % 60:02d}:00",
                        })
                except BaseException as exc:  # pragma: no cover - failure path
                    errors.append(exc)

            threads = [
                threading.Thread(target=add_jobs, args=(group * 20, 20))
                for group in range(5)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            self.assertEqual(errors, [])
            ids = sorted(job["id"] for job in store.list_jobs())
            self.assertEqual(len(ids), 100)
            self.assertEqual(ids, [f"job-{i:03d}" for i in range(100)])

    def test_concurrent_processes_do_not_lose_job_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = AppPaths(root / "state", root / "agents")
            paths.ensure()

            worker = (
                "import os, sys\n"
                "from pathlib import Path\n"
                "from prompt_scheduler.paths import AppPaths\n"
                "from prompt_scheduler.storage import JobStore\n"
                "data_dir = Path(os.environ['PS_TEST_DATA_DIR'])\n"
                "agents_dir = Path(os.environ['PS_TEST_AGENTS_DIR'])\n"
                "start = int(sys.argv[1])\n"
                "count = int(sys.argv[2])\n"
                "store = JobStore(AppPaths(data_dir, agents_dir))\n"
                "for i in range(start, start + count):\n"
                "    store.add({'id': f'proc-{i:03d}', 'name': f'p-{i}', 'created_at': '2026-01-01T00:00:00'})\n"
            )

            env = {
                **os.environ,
                "PS_TEST_DATA_DIR": str(paths.data_dir),
                "PS_TEST_AGENTS_DIR": str(paths.launch_agents_dir),
            }
            procs = [
                subprocess.Popen(
                    [sys.executable, "-c", worker, str(group * 10), "10"],
                    env=env,
                )
                for group in range(4)
            ]
            for proc in procs:
                self.assertEqual(proc.wait(timeout=30), 0)

            ids = sorted(job["id"] for job in JobStore(paths).list_jobs())
            self.assertEqual(len(ids), 40)
            self.assertEqual(ids, [f"proc-{i:03d}" for i in range(40)])

    def test_concurrent_state_record_resets_do_not_lose_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = AppPaths(root / "state", root / "agents")
            store = StateStore(paths)
            errors: list[BaseException] = []

            def write_keys(start: int, count: int) -> None:
                try:
                    for i in range(start, start + count):
                        store.record_reset({f"key_{i:03d}": i})
                except BaseException as exc:  # pragma: no cover - failure path
                    errors.append(exc)

            threads = [
                threading.Thread(target=write_keys, args=(group * 25, 25))
                for group in range(4)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            self.assertEqual(errors, [])
            payload = store.load()
            for i in range(100):
                self.assertEqual(payload.get(f"key_{i:03d}"), i)


if __name__ == "__main__":
    unittest.main()
