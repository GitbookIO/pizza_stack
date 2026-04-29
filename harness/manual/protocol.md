# TomatoPy Benchmark — Manual Run Protocol

This document describes how to run the benchmark manually against agent systems
that cannot be automated: Claude Code, Cursor, and Codex CLI. Manual runs are
first-class benchmark data. Results are collected using the same session ID
convention as automated runs and joined against server logs for analysis.

---

## Run phases

The benchmark runs in two phases, each supporting a different blog post.

**Phase 1 — Baseline (Post 1)**
Run the baseline prompt across all three agent systems. The goal is to establish
whether front-loading docs and recovering through errors is a pattern shared
across agents, not just Claude Code. No interventions — pure baseline.

| | Baseline |
|---|---|
| Claude Code | 3 runs |
| Codex CLI | 3 runs |
| Cursor | 3 runs |

**Phase 2 — Interventions (Post 2)**
Run intervention conditions on Claude Code only, since it produces the richest
parseable transcript. The goal is to test whether read-first prompting or
MCP access changes doc-reading behaviour.

| | Read-First | MCP-Undirected |
|---|---|---|
| Claude Code | 3 runs | 3 runs |

Total: **15 runs** across both phases, all on GitBook docs.

---

## Directory Structure

```
harness/manual/
├── protocol.md          # This file
├── session_generator.py # Generates a session ID and prints the ready-to-paste prompt
├── log.csv              # Running log of all manual runs
└── traces/              # Saved transcripts per run
    ├── <session_id>.jsonl           # Claude Code or Codex CLI JSONL transcript
    ├── <session_id>_cursor.jsonl    # Cursor native JSONL transcript
    └── <session_id>_mcp.json        # MCP query log (mcp-undirected condition)
```

---

## Step 0: Clean Agent Memory

Agent systems may persist knowledge between sessions. If the agent remembers
PizzaStack from a prior run, it can pass without reading the docs — invalidating
the benchmark. **Before every run:**

**Claude Code**
```bash
ls ~/.claude/memory/
```
Delete any files mentioning PizzaStack, TomatoPy, or pizza_bench.

**Cursor**
Check `.cursor/` in the project directory and delete any rules or memory files
that reference PizzaStack or TomatoPy. Use a fresh empty project for each run.

**Codex CLI**
```bash
ls ~/.codex/
```
Check for any `AGENTS.md` or rules files in the run directory that reference
PizzaStack. The session generator prints a fresh temp directory — always use it.

---

## Step 1: Generate a Session ID and Prompt

Run the session generator before every run. It prints a fresh UUID, the
complete task prompt, and a fresh temp directory to run from.

```bash
# Phase 1 — baseline, any agent
python harness/manual/session_generator.py \
  --platform gitbook \
  --framing baseline \
  --agent-system claude-code \   # or: cursor, codex
  --model claude-sonnet-4-6 \    # or: o4-mini, claude-sonnet-4-6
  --run-index 0

# Phase 2 — read-first, Claude Code only
python harness/manual/session_generator.py \
  --platform gitbook \
  --framing read-first \
  --agent-system claude-code \
  --model claude-sonnet-4-6 \
  --run-index 0

# Phase 2 — MCP-undirected, Claude Code only
python harness/manual/session_generator.py \
  --platform gitbook-mcp \
  --framing mcp-undirected \
  --agent-system claude-code \
  --model claude-sonnet-4-6 \
  --run-index 0
```

The output includes a memory-check reminder, a `cd` command for the clean temp
directory, and the prompt to paste.

---

## Step 2: Run the Agent

Paste the prompt into the agent system and let it run without intervention.
Only intervene if the agent gets completely stuck in a loop or crashes — note
any intervention in the `notes` column of `log.csv`.

### Claude Code

Run from the fresh temp directory printed by the session generator:

```bash
cd <temp_dir>
claude
```

Paste the prompt. Claude Code writes and executes Python directly. Watch the
tool calls in the terminal. The session UUID is visible in the terminal header
at session start — note it, as it is the JSONL filename (different from the
benchmark session UUID).

For MCP-undirected runs, verify the tomatopy-docs server is connected before
pasting the prompt:
```bash
/mcp
# Confirm 'tomatopy-docs' appears with searchDocumentation and getPage
# If not: claude mcp add --transport http tomatopy-docs https://tomatopy.pizza/docs/~gitbook/mcp
```

### Codex CLI

Run from the fresh temp directory:

```bash
cd <temp_dir>
codex
```

Paste the prompt. Codex CLI saves a full JSONL session transcript automatically
to `~/.codex/sessions/YYYY/MM/DD/rollout-<timestamp>-<id>.jsonl`. This includes
tool calls and outputs and is parseable in the same way as Claude Code transcripts.

To stream and save output simultaneously:
```bash
codex exec "$(cat prompt.txt)" --json | tee harness/manual/traces/<session_id>.jsonl
```

### Cursor

Open a fresh empty project folder. Use Agent mode. Paste the prompt into the
Agent input.

Cursor automatically writes JSONL transcript files to `.cursor/projects/` within
your workspace. After the run, locate the relevant file:

```bash
ls <project_dir>/.cursor/projects/
```

**Important limitation:** Cursor's JSONL transcripts currently include tool
inputs but not tool outputs (a known open bug). This means you can extract
`docs_fetch_count`, `docs_fetch_timing`, and `first_action` from the URL
patterns in tool inputs, but cannot see what the docs returned or what API
errors the agent encountered. Server-side logs cover the API error question.
Note this limitation in the `notes` column.

The `parse_transcript.py` script requires a Cursor-specific adapter because
the JSONL schema differs from Claude Code's. Until that adapter is built,
extract behavioural metrics manually by reading the transcript and recording
them directly into `log.csv`.

---

## Step 2b: Save the Transcript

Before closing the session, save the transcript to `traces/`.

**Claude Code**

The JSONL file lives at:
```
~/.claude/projects/<encoded-working-dir>/<claude-code-session-uuid>.jsonl
```

Find it:
```bash
ls ~/.claude/projects/
# Match the directory to the temp path from session_generator.py
```

Copy it:
```bash
cp ~/.claude/projects/<dir>/<uuid>.jsonl \
   harness/manual/traces/<benchmark_session_id>.jsonl
```

Also run `/export` inside the session to save a human-readable version:
```bash
/export harness/manual/traces/<benchmark_session_id>_conversation.md
```

**Codex CLI**

The JSONL transcript is at:
```
~/.codex/sessions/YYYY/MM/DD/rollout-<timestamp>-<id>.jsonl
```

Copy it:
```bash
cp ~/.codex/sessions/.../<rollout>.jsonl \
   harness/manual/traces/<benchmark_session_id>.jsonl
```

**Cursor**

Copy the native JSONL from the workspace:
```bash
cp <project_dir>/.cursor/projects/<file>.jsonl \
   harness/manual/traces/<benchmark_session_id>_cursor.jsonl
```

---

## Step 3: Record the Result

After each run, add one row to `harness/manual/log.csv`.

### log.csv columns

| Column | Description |
|---|---|
| `session_id` | UUID from session_generator.py |
| `agent_system` | `claude-code`, `cursor`, or `codex` |
| `model` | Model used, e.g. `claude-sonnet-4-6`, `o4-mini` |
| `platform` | `gitbook` or `gitbook-mcp` |
| `run_index` | 0, 1, or 2 |
| `prompt_framing` | `baseline`, `read-first`, or `mcp-undirected` |
| `passed` | `true` or `false` based on agent's printed output |
| `final_score` | The `overall_score` the agent printed, e.g. `0.94` |
| `correct_pipeline` | `true` if agent sliced before simmer and assembled before bake |
| `docs_fetch_count` | Number of docs fetches observed in transcript |
| `docs_fetch_timing` | `before_first_api_call`, `after_first_api_call`, or `never` |
| `first_action` | `docs_fetch`, `api_call`, or `other` |
| `used_mcp_for_docs` | `true` if agent used MCP tools for docs access |
| `transcript_saved` | `true` if transcript copied to `traces/` |
| `notes` | Interventions, errors, Cursor tool-output limitation, observations |
| `timestamp` | ISO timestamp when the run completed |

### Example rows

```csv
session_id,agent_system,model,platform,run_index,prompt_framing,passed,final_score,correct_pipeline,docs_fetch_count,docs_fetch_timing,first_action,used_mcp_for_docs,transcript_saved,notes,timestamp
a1b2c3d4-...,claude-code,claude-sonnet-4-6,gitbook,0,baseline,true,0.94,true,1,before_first_api_call,docs_fetch,false,true,,2026-04-01T14:23:00Z
e5f6g7h8-...,cursor,claude-sonnet-4-6,gitbook,0,baseline,false,0.41,false,1,before_first_api_call,docs_fetch,false,true,cursor_tool_outputs_redacted,2026-04-01T14:51:00Z
i9j0k1l2-...,codex,o4-mini,gitbook,0,baseline,true,0.92,true,2,before_first_api_call,docs_fetch,false,true,,2026-04-01T15:10:00Z
m3n4o5p6-...,claude-code,claude-sonnet-4-6,gitbook-mcp,0,mcp-undirected,true,0.95,true,0,never,docs_fetch,true,true,,2026-04-01T15:30:00Z
```

---

## Step 4: Verify Against Server Logs

After each run, check the API server logs for the session ID to confirm what
actually happened.

Key things to verify:

- Did the agent call `/v1/tomato/slice` before `/v1/cook/simmer`?
- Did the agent call `/v1/pizza/assemble` before `/v1/pizza/bake`?
- Which docs pages did it fetch, and in what order?
- Did it check `llms.txt`?

If the agent printed PASS but server logs show a degraded pipeline, record
`passed: true` (what the agent reported) and `correct_pipeline: false` (what
the logs show). Both data points are meaningful.

---

## Transcript formats by agent

| Agent | Transcript location | Format | Tool calls | Tool outputs | Auto-parseable |
|---|---|---|---|---|---|
| Claude Code | `~/.claude/projects/<dir>/<uuid>.jsonl` | JSONL | ✓ | ✓ | Yes — `parse_transcript.py` |
| Codex CLI | `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` | JSONL | ✓ | ✓ | Needs Codex adapter |
| Cursor | `<project>/.cursor/projects/*.jsonl` | JSONL | ✓ | ✗ (redacted) | Manual extraction for now |

The Cursor tool-output limitation is a known open bug. Tool inputs are present,
which is sufficient to extract docs fetch count, timing, and first action from
URL patterns. Note this in your methodology writeup.

---

## MCP Condition (Phase 2 only)

The `mcp-undirected` condition tests whether Claude Code uses the GitBook MCP
server when it is available but the prompt says nothing about it. This isolates
the effect of tool availability from explicit instruction.

Setup — add the server once in Claude Code's global config:
```bash
claude mcp add --transport http tomatopy-docs https://tomatopy.pizza/docs/~gitbook/mcp
```

Before each MCP run, verify it is connected:
```bash
/mcp
# Confirm tomatopy-docs appears with searchDocumentation and getPage
```

If the agent falls back to WebFetch for docs despite MCP being available, record
`used_mcp_for_docs: false` and note `mcp_fallback: true` in the `notes` column.
This itself is a finding.

---

## Tips

- Always use a fresh project/directory for each run. Existing files influence
  agent behaviour unpredictably.
- If the agent asks a clarifying question, respond only with "follow the
  documentation." Do not provide hints.
- If the agent fails to find the docs at all and gives up, record
  `passed: false`, `final_score: 0`, and note `did_not_find_docs: true`.
- Save transcripts even for failed runs — the failure path is often more
  interesting than the success path.
- Run all three Phase 1 baseline cells before starting Phase 2. The baseline
  data frames the intervention findings.