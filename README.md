# Claude Session Scheduler

Lightweight local macOS CLI for scheduling Claude Code prompts through user-level
`launchd`.

## Install for development

```bash
python3 -m pip install -e .
```

## Happy path

```bash
claude-session-scheduler setup
claude-session-scheduler add
claude-session-scheduler status
```

`setup` checks your Mac, helps install Claude Code if it is missing, and offers
to create your first schedule.

## Common commands

```bash
claude-session-scheduler setup

claude-session-scheduler add \
  --name morning-review \
  --cwd /path/to/project \
  --daily "09:00" \
  --prompt "Review TODOs and summarize risks."

claude-session-scheduler list
claude-session-scheduler remove JOB_ID
claude-session-scheduler status
claude-session-scheduler logs JOB_ID

claude-session-scheduler start-now --cwd /path/to/project
claude-session-scheduler start-at-reset --cwd /path/to/project
claude-session-scheduler install-statusline
```

The older nested commands still work for scripts:

```bash
claude-session-scheduler doctor

claude-session-scheduler schedule add \
  --name morning-review \
  --cwd /path/to/project \
  --daily "09:00" \
  --prompt "Review TODOs and summarize risks."

claude-session-scheduler schedule list
claude-session-scheduler schedule remove JOB_ID
claude-session-scheduler logs JOB_ID

claude-session-scheduler window start-now --cwd /path/to/project
claude-session-scheduler window start-at-reset --cwd /path/to/project
```

If `setup` cannot find Claude Code, it will ask whether to install it using
Anthropic's standard npm command:

```bash
npm install -g @anthropic-ai/claude-code
```

For non-interactive setup:

```bash
claude-session-scheduler setup --yes
```

Scheduled jobs run:

```bash
claude -p --max-turns 1 --no-session-persistence --output-format json "<prompt>"
```

The session starter sends a tiny prompt:

```text
Reply with exactly OK.
```

## Claude login

The scheduler checks `claude auth status --json` separately from the Claude Code
install check. If Claude Code is installed but not signed in, setup/status report
that login is required, the macOS app disables manual sends, and scheduled runs
record `auth_required` without sending the prompt.

Sign in with:

```bash
claude auth login
```

## Local state

State is stored in:

```text
~/.local/share/claude-session-scheduler/
```

LaunchAgents are installed in:

```text
~/Library/LaunchAgents/
```

For tests or isolated development, these can be overridden:

```bash
CLAUDE_SESSION_SCHEDULER_HOME=/tmp/css-state
CLAUDE_SESSION_SCHEDULER_LAUNCH_AGENTS_DIR=/tmp/css-agents
```

## Reset detection

The tool records observed reset times when Claude explicitly reports them in
command output, such as `usage limit reached, resets at 5:00 PM`.

For current Claude Code subscription usage, install the optional status-line
bridge:

```bash
claude-session-scheduler install-statusline
```

Claude Code then sends its status-line JSON to the scheduler after API
responses. When the JSON includes `rate_limits.five_hour`, the scheduler stores
the current 5-hour usage percentage and reset time, and uses that reset as the
next observed reset. If you already have a custom Claude Code status line,
`install-statusline` will refuse to overwrite it unless you pass `--force`.

It also records an estimated reset after a successful scheduler-started Claude
session. The estimate assumes a five-hour usage window and is labeled separately
from observed resets. The status-line bridge is preferred when available because
it uses Claude Code's own `rate_limits` data.
