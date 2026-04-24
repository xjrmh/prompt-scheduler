# Prompt Scheduler

Lightweight local macOS CLI for scheduling Claude Code or Codex prompts through
user-level `launchd`.

## Install for development

```bash
python3 -m pip install -e .
```

## Happy path

```bash
prompt-scheduler setup
prompt-scheduler add
prompt-scheduler status
```

`setup` checks your Mac, helps install a missing prompt provider, and offers to
create your first schedule. Existing schedules without a provider keep using
Claude Code; pass `--provider codex` for Codex schedules.

## Common commands

```bash
prompt-scheduler setup

prompt-scheduler add \
  --provider codex \
  --name morning-review \
  --cwd /path/to/project \
  --daily "09:00" \
  --prompt "Review TODOs and summarize risks."

prompt-scheduler list
prompt-scheduler remove JOB_ID
prompt-scheduler status
prompt-scheduler logs JOB_ID

prompt-scheduler start-now --provider codex --cwd /path/to/project
prompt-scheduler start-at-reset --cwd /path/to/project
prompt-scheduler install-statusline
```

The older nested commands still work for scripts:

```bash
prompt-scheduler doctor

prompt-scheduler schedule add \
  --provider codex \
  --name morning-review \
  --cwd /path/to/project \
  --daily "09:00" \
  --prompt "Review TODOs and summarize risks."

prompt-scheduler schedule list
prompt-scheduler schedule remove JOB_ID
prompt-scheduler logs JOB_ID

prompt-scheduler window start-now --provider codex --cwd /path/to/project
prompt-scheduler window start-at-reset --cwd /path/to/project
```

If `setup` cannot find the selected provider, it will ask whether to install it
using npm. Claude Code uses:

```bash
npm install -g @anthropic-ai/claude-code
```

Codex uses:

```bash
npm install -g @openai/codex
```

For non-interactive setup:

```bash
prompt-scheduler setup --yes
prompt-scheduler setup --provider codex --yes
```

Claude Code jobs run:

```bash
claude -p --max-turns 1 --no-session-persistence --output-format json "<prompt>"
```

Codex jobs run non-interactively with an ephemeral session:

```bash
codex exec --cd /path/to/project --skip-git-repo-check --ask-for-approval never --sandbox workspace-write --ephemeral "<prompt>"
```

The manual session starter sends a tiny prompt:

```text
Reply with exactly OK.
```

## Provider login

The scheduler checks `claude auth status --json` separately from the Claude Code
install check. If Claude Code is installed but not signed in, setup/status report
that login is required, the macOS app disables manual sends, and scheduled runs
record `auth_required` without sending the prompt.

Sign in with:

```bash
claude auth login
```

For Codex, the scheduler checks `codex login status`. Sign in with:

```bash
codex login
```

Set `PROMPT_SCHEDULER_PROVIDER=codex` to make Codex the default provider for new
CLI-created schedules, or pass `--provider codex` per command.

## Local state

State is stored in:

```text
~/.local/share/prompt-scheduler/
```

LaunchAgents are installed in:

```text
~/Library/LaunchAgents/
```

For tests or isolated development, these can be overridden:

```bash
PROMPT_SCHEDULER_HOME=/tmp/prompt-scheduler-state
PROMPT_SCHEDULER_LAUNCH_AGENTS_DIR=/tmp/prompt-scheduler-agents
```

## Reset detection

The tool records observed reset times when a provider explicitly reports them in
command output, such as `usage limit reached, resets at 5:00 PM`.

For current Claude Code subscription usage, install the optional status-line
bridge:

```bash
prompt-scheduler install-statusline
```

Claude Code then sends its status-line JSON to the scheduler after API
responses. When the JSON includes `rate_limits.five_hour`, the scheduler stores
the current 5-hour usage percentage and reset time, and uses that reset as the
next observed reset. If you already have a custom Claude Code status line,
`install-statusline` will refuse to overwrite it unless you pass `--force`.

It also records an estimated reset after a successful scheduler-started Claude
Code session. The estimate assumes a five-hour usage window and is labeled
separately from observed resets. The status-line bridge is preferred when
available because it uses Claude Code's own `rate_limits` data.
