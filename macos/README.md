# Prompt Scheduler macOS Menu Bar App

Local SwiftUI menu bar companion for Prompt Scheduler.
Schedule creation and removal stay in the Python CLI; the macOS app exposes
setup status, manual sends, last-run status, log reveal, and quit actions from
the menu bar.

The menu bar app follows the CLI's active provider. If Codex is the only signed
in provider, manual sends run through Codex; otherwise use
`PROMPT_SCHEDULER_PROVIDER=codex` or CLI `--provider codex` flags to prefer it.

## Run

From the repository root:

```bash
python3 -m pip install -e .
cd macos
swift run PromptSchedulerUI
```

To build a local clickable app prototype:

```bash
cd macos
Scripts/build_app.sh
open ".build/Prompt Scheduler.app"
```

The app calls the Python CLI through JSON commands. For development without
installing the CLI, the shared engine client falls back to:

```bash
python3 -m prompt_scheduler
```

with the repository `src` directory on `PYTHONPATH`.

You can force a specific CLI path:

```bash
PROMPT_SCHEDULER_BIN=/path/to/prompt-scheduler \
  swift run PromptSchedulerUI
```

## Test

```bash
cd macos
swift test
```
