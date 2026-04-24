# Claude Session Scheduler macOS UI

Local SwiftUI menu bar prototype for Claude Session Scheduler.

## Run

From the repository root:

```bash
python3 -m pip install -e .
cd macos
swift run ClaudeSessionSchedulerUI
```

To build a local clickable app prototype:

```bash
cd macos
Scripts/build_app.sh
open ".build/Claude Session Scheduler.app"
```

The app calls the Python CLI through JSON commands. For development without
installing the CLI, the shared engine client falls back to:

```bash
python3 -m claude_session_scheduler
```

with the repository `src` directory on `PYTHONPATH`.

You can force a specific CLI path:

```bash
CLAUDE_SESSION_SCHEDULER_BIN=/path/to/claude-session-scheduler \
  swift run ClaudeSessionSchedulerUI
```

## Test

```bash
cd macos
swift test
```
