# TomatoPy Agent Docs Benchmark

A benchmark testing whether AI coding agents actually read API documentation — or just guess and recover from errors.

The test surface is **PizzaStack**, a fictional pizza-making API by **TomatoPy**. Neither exists in any model's training data, making it a clean, controlled test of doc-reading behaviour rather than training data recall.

---

## Research Questions

1. Do agents read docs, or do they infer the API from common sense and recover from errors?
2. When given both a structured docs tool (MCP) and a web fetch tool, which do agents reach for?
3. Does explicitly prompting agents to read docs before writing code change their behaviour?

---

## How It Works

Each benchmark run gives an agent a task prompt, an API key, a session ID, and a docs URL. The agent must complete a multi-step pizza pipeline using the PizzaStack API. Two hidden quality traps test whether it actually read the docs:

- **Slice before simmer:** Raw tomato IDs passed to `/cook/simmer` return HTTP 200 but with `sauce_quality: "degraded"`. The agent must call `/tomato/slice` first — documented but not enforced by the schema.
- **Assemble before bake:** `/pizza/bake` requires a `pizza_id` from `/pizza/assemble`. Passing a `base_id` directly returns HTTP 400.

Quality propagates through the pipeline. A correct run scores 0.90–0.98. A degraded run scores 0.35–0.50. The agent is asked to print PASS or FAIL based on the score.

Behavioral analysis comes from two sources:
- **Claude Code JSONL transcripts** — which tools the agent called, in what order, and whether it fetched docs before or after making API calls
- **Server-side API logs** — what endpoints were called, with what parameters, and in what order

---

## Repository Structure

```
pizza_stack/
├── api/                        # FastAPI backend (PizzaStack API)
│   ├── main.py
│   ├── models.py
│   ├── logic.py                # Quality scoring + session store
│   ├── logger.py               # JSONL request logging
│   ├── openapi.yaml            # Canonical OpenAPI spec
│   └── routes/
├── harness/
│   └── manual/                 # Manual run protocol (active)
│       ├── protocol.md         # Step-by-step guide
│       ├── session_generator.py
│       ├── record_result.py
│       ├── log.csv
│       └── traces/
├── analysis/
│   ├── parse_transcript.py     # Parses Claude Code JSONL transcripts
│   ├── score.py                # Scoring + summary tables
│   └── report.py               # Markdown report generation
├── docs-platforms/             # Platform deployment configs (future)
├── requirements.txt
└── project_spec.md
```

---

## Prerequisites

- Python 3.11+
- The PizzaStack API running at `https://api.tomatopy.pizza` (or locally)

```bash
pip install -r requirements.txt
```

---

## Running a Session

### 1. Generate a session ID and prompt

```bash
python harness/manual/session_generator.py \
  --platform gitbook \
  --agent-system claude-code \
  --model claude-opus-4-6 \
  --run-index 0 \
  --api-key "your-benchmark-key"
```

Add `--framing read-first` to test the variant prompt that explicitly instructs the agent to read docs before writing code.

### 2. Run the agent

Paste the printed prompt into a fresh Claude Code (or Cursor, Codex, Copilot) session. See `harness/manual/protocol.md` for agent-specific instructions, memory-clearing steps, and how to save transcripts.

### 3. Record the result

```bash
python harness/manual/record_result.py \
  --session-id <uuid> \
  --api-key "your-benchmark-key" \
  --agent-system claude-code \
  --model claude-opus-4-6 \
  --platform gitbook \
  --run-index 0 \
  --transcript ~/.claude/projects/<encoded-dir>/<session>.jsonl
```

### 4. Analyse

```bash
# Parse a single transcript
python analysis/parse_transcript.py \
  --transcript ~/.claude/projects/<encoded-dir>/<session>.jsonl \
  --session-id <uuid>

# Summary tables across all runs
python -m analysis.score

# Full markdown report
python -m analysis.report
```

---

## Conditions

| Condition | Prompt | Docs access |
|---|---|---|
| Baseline | Standard task prompt | Web fetch to docs URL |
| Read-first | Adds "read docs before writing code" | Web fetch to docs URL |
| MCP | Directs agent to use GitBook MCP | GitBook MCP server |

---

## API Backend

The PizzaStack API is a FastAPI app deployed at `https://api.tomatopy.pizza`. To run locally:

```bash
export PIZZASTACK_API_KEY="your-key"
export PIZZASTACK_DATA_DIR="./data"
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

---

## Related Work

This benchmark is methodologically complementary to [Dachary Carey's agent docs research](https://dacharycarey.com). Her work observes how agents access real-world documentation; this benchmark uses a fictional, never-trained-on API to isolate doc-reading behaviour from training data recall.
