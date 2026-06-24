## Agent skills

### Issue tracker

GitHub Issues are the tracker for this repo, and external PRs are not a triage surface. See `docs/agents/issue-tracker.md`.

### Triage labels

Use the default triage vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, and `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout: one root `CONTEXT.md` plus `docs/adr/` for architecture decisions. See `docs/agents/domain.md`.

### Python execution

All Python execution in this repo goes through the `py3env/` virtualenv symlink in the
project root — including `pytest` and any other Python commands. Use `py3env/bin/python`,
`py3env/bin/pytest`, etc. (or activate `py3env/bin/activate` first). Never invoke a global
`python`/`python3`/`pytest`.

### finance CLI

Always run `finance` commands via `bin/finance` (the repo wrapper), not `py3env/bin/finance`
directly. When running inside a Claude job (`$CLAUDE_JOB_DIR` is set), the wrapper tees output
to a timestamped log and prints a `tail -f` line so the user can watch live. Outside that
context it's a transparent passthrough with no overhead.
