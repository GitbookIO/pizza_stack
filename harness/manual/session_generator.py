#!/usr/bin/env python3
"""Generate a session ID and ready-to-paste prompt for manual benchmark runs."""

import uuid
import argparse
import tempfile
import os

# ---------------------------------------------------------------------------
# Web fetch conditions (platform: gitbook, mintlify, etc.)
# ---------------------------------------------------------------------------

PROMPT_BASELINE = """You are a developer using the PizzaStack API by TomatoPy for the first time.

Documentation is available at: {docs_url}

Your task: Write and execute a Python script that uses the PizzaStack API to:
1. Acquire a San Marzano tomato (ripeness 0.8, weight 150g)
2. Prepare it correctly for cooking
3. Simmer it into a sauce
4. Create a neapolitan pizza base (12 inch, thin)
5. Assemble the pizza with the sauce and at least one topping
6. Bake the pizza at an appropriate temperature

Use API key: {api_key}
Use session ID: {session_id}  — pass this as X-Session-ID on every request to the API.
"""

PROMPT_READ_FIRST = """You are a developer using the PizzaStack API by TomatoPy for the first time.

Documentation is available at: {docs_url}
Before writing any code, read the documentation at the URL above.

Your task: Write and execute a Python script that uses the PizzaStack API to:
1. Acquire a San Marzano tomato (ripeness 0.8, weight 150g)
2. Prepare it correctly for cooking
3. Simmer it into a sauce
4. Create a neapolitan pizza base (12 inch, thin)
5. Assemble the pizza with the sauce and at least one topping
6. Bake the pizza at an appropriate temperature

Use API key: {api_key}
Use session ID: {session_id}  — pass this as X-Session-ID on every request to the API.
"""

# ---------------------------------------------------------------------------
# MCP conditions (platform: gitbook-mcp)
#
# Three variants testing how much scaffolding the agent needs before it will
# use a structured docs tool rather than defaulting to web fetch:
#
#   mcp-undirected  — MCP is connected but the prompt says nothing about it.
#                     Does the agent discover and use MCP tools on its own?
#
#   mcp-hinted      — Prompt mentions an MCP server is available but does not
#                     name the server or its tools. Does the hint suffice?
#
#   mcp-explicit    — Prompt names the server (tomatopy-docs) and both tools
#                     (searchDocumentation, getPage). Ceiling condition.
# ---------------------------------------------------------------------------

PROMPT_MCP_UNDIRECTED = """You are a developer using the PizzaStack API by TomatoPy for the first time.

Documentation is available at: https://tomatopy.pizza/docs

Your task: Write and execute a Python script that uses the PizzaStack API to:
1. Acquire a San Marzano tomato (ripeness 0.8, weight 150g)
2. Prepare it correctly for cooking
3. Simmer it into a sauce
4. Create a neapolitan pizza base (12 inch, thin)
5. Assemble the pizza with the sauce and at least one topping
6. Bake the pizza at an appropriate temperature

Use API key: {api_key}
Use session ID: {session_id}  — pass this as X-Session-ID on every request to the API.
"""

PROMPT_MCP_HINTED = """You are a developer using the PizzaStack API by TomatoPy for the first time.

Documentation is available via an MCP server connected to this session.
Use the MCP server to look up the PizzaStack API documentation.

Your task: Write and execute a Python script that uses the PizzaStack API to:
1. Acquire a San Marzano tomato (ripeness 0.8, weight 150g)
2. Prepare it correctly for cooking
3. Simmer it into a sauce
4. Create a neapolitan pizza base (12 inch, thin)
5. Assemble the pizza with the sauce and at least one topping
6. Bake the pizza at an appropriate temperature

Use API key: {api_key}
Use session ID: {session_id}  — pass this as X-Session-ID on every request to the API.
"""

PROMPT_MCP_EXPLICIT = """You are a developer using the PizzaStack API by TomatoPy for the first time.

Documentation is available via the tomatopy-docs MCP server connected to this session.
Use the searchDocumentation and getPage tools from that server to read the docs
before writing any code. Do not fetch documentation via web URLs.

Your task: Write and execute a Python script that uses the PizzaStack API to:
1. Acquire a San Marzano tomato (ripeness 0.8, weight 150g)
2. Prepare it correctly for cooking
3. Simmer it into a sauce
4. Create a neapolitan pizza base (12 inch, thin)
5. Assemble the pizza with the sauce and at least one topping
6. Bake the pizza at an appropriate temperature

Use API key: {api_key}
Use session ID: {session_id}  — pass this as X-Session-ID on every request to the API.
"""

# ---------------------------------------------------------------------------
# Platform → docs URL mapping
# ---------------------------------------------------------------------------

PLATFORMS = {
    "gitbook": "https://tomatopy.pizza/docs",
    "gitbook-mcp": None,  # MCP conditions — no docs URL, uses MCP server
    "mintlify": "https://mintlify.tomatopy.pizza/docs",
    "docusaurus": "https://docusaurus.tomatopy.pizza/docs",
    "readme": "https://readme.tomatopy.pizza/docs",
    "github-pages": "https://pages.tomatopy.pizza/docs",
}

# Framing options per platform type
WEB_FRAMINGS = ["baseline", "read-first"]
MCP_FRAMINGS = ["mcp-undirected", "mcp-hinted", "mcp-explicit"]
ALL_FRAMINGS = WEB_FRAMINGS + MCP_FRAMINGS

MCP_TEMPLATES = {
    "mcp-undirected": PROMPT_MCP_UNDIRECTED,
    "mcp-hinted":     PROMPT_MCP_HINTED,
    "mcp-explicit":   PROMPT_MCP_EXPLICIT,
}

WEB_TEMPLATES = {
    "baseline":   PROMPT_BASELINE,
    "read-first": PROMPT_READ_FIRST,
}

API_KEY = "BENCHMARK_API_KEY"  # Replace with real key before running


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a session ID and prompt for manual benchmark runs")
    parser.add_argument("--platform", default="gitbook", choices=PLATFORMS.keys())
    parser.add_argument("--api-key", default=API_KEY, help="PizzaStack API key")
    parser.add_argument("--agent-system", required=True,
                        help="e.g. claude-code, cursor, codex, copilot")
    parser.add_argument("--model", required=True,
                        help="e.g. claude-opus-4-6, claude-sonnet-4-6, gpt-4o")
    parser.add_argument("--run-index", type=int, default=0,
                        help="Run index within the cell (0, 1, or 2)")
    parser.add_argument("--framing", default=None, choices=ALL_FRAMINGS,
                        help=(
                            "Prompt framing variant. "
                            "Web fetch conditions: baseline (default), read-first. "
                            "MCP conditions: mcp-undirected (default), mcp-hinted, mcp-explicit."
                        ))
    args = parser.parse_args()

    # Default framing based on platform
    is_mcp = args.platform == "gitbook-mcp"
    if args.framing is None:
        args.framing = "mcp-undirected" if is_mcp else "baseline"

    # Validate framing matches platform type
    if is_mcp and args.framing in WEB_FRAMINGS:
        parser.error(f"Framing '{args.framing}' is for web fetch conditions. "
                     f"For gitbook-mcp use one of: {', '.join(MCP_FRAMINGS)}")
    if not is_mcp and args.framing in MCP_FRAMINGS:
        parser.error(f"Framing '{args.framing}' is for MCP conditions. "
                     f"For web fetch platforms use one of: {', '.join(WEB_FRAMINGS)}")

    session_id = str(uuid.uuid4())
    tmpdir = tempfile.mkdtemp(prefix=f"pizza_bench_{session_id[:8]}_")
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # Create requirements.txt so agents can install dependencies
    req_path = os.path.join(tmpdir, "requirements.txt")
    with open(req_path, "w") as f:
        f.write("requests\n")

    # Create a venv with requests pre-installed
    venv_path = os.path.join(tmpdir, ".venv")
    os.system(f"python3 -m venv {venv_path} && {venv_path}/bin/pip install requests -q")

    record_script = os.path.join(script_dir, "record_result.py")

    prompt_vars = dict(api_key=args.api_key, session_id=session_id)

    if is_mcp:
        prompt = MCP_TEMPLATES[args.framing].format(**prompt_vars)
        print(f"Session ID: {session_id}")
        print(f"Platform:   {args.platform}")
        print(f"Framing:    {args.framing}")
        print(f"Docs via:   tomatopy-docs MCP server (https://tomatopy.pizza/docs/~gitbook/mcp)")
        print(f"Run dir:    {tmpdir}")
        print(f"NOTE:       .venv with requests pre-installed created in run dir")
        print("")
        print("NOTE: Before pasting the prompt, verify the MCP server is connected:")
        print("  1. Open a Claude Code session in the run directory")
        print("  2. Run /mcp and confirm 'tomatopy-docs' appears with searchDocumentation and getPage")
        print("  3. If not connected: claude mcp add --transport http tomatopy-docs https://tomatopy.pizza/docs/~gitbook/mcp")
    else:
        docs_url = PLATFORMS[args.platform]
        prompt = WEB_TEMPLATES[args.framing].format(docs_url=docs_url, **prompt_vars)
        print(f"Session ID: {session_id}")
        print(f"Platform:   {args.platform}")
        print(f"Framing:    {args.framing}")
        print(f"Docs URL:   {docs_url}")
        print(f"Run dir:    {tmpdir}")
        print(f"NOTE:       .venv with requests pre-installed created in run dir")

    record_cmd = (
        f"python {record_script}"
        f" --session-id {session_id}"
        f" --api-key {args.api_key}"
        f" --agent-system {args.agent_system}"
        f" --model {args.model}"
        f" --platform {args.platform}"
        f" --run-index {args.run_index}"
        f" --framing {args.framing}"
        f" --transcript-file <transcript-filename>"
    )

    print("")
    print("BEFORE RUNNING — check for leaked memory from prior runs:")
    if args.agent_system == "claude-code":
        print(f"  ls ~/.claude/memory/")
        print(f"  # Delete any PizzaStack/TomatoPy-related files found there")
    elif args.agent_system == "codex":
        print(f"  ls ~/.codex/")
        print(f"  # Check for any AGENTS.md or rules files referencing PizzaStack in the run directory")
    elif args.agent_system == "cursor":
        print(f"  # Check .cursor/ in the project directory for any rules or memory files referencing PizzaStack")
    else:
        print(f"  # Check for any agent memory or rules files referencing PizzaStack/TomatoPy")
    print("")
    if args.agent_system in ("claude-code", "codex"):
        print(f"Start the agent session from the clean directory:")
        print(f"  cd {tmpdir}")
        print(f"  source .venv/bin/activate")
        print(f"  {'claude' if args.agent_system == 'claude-code' else 'codex'}   # or: {'codex' if args.agent_system == 'claude-code' else 'claude'}")
    elif args.agent_system == "cursor":
        print(f"Start the agent session:")
        print(f"  Open {tmpdir} as a new project in Cursor (File > Open Folder)")
        print(f"  .venv with requests pre-installed will be detected automatically")
        print(f"  Use Agent mode and paste the prompt")
    else:
        print(f"Start the agent session from the clean directory:")
        print(f"  cd {tmpdir}")
        print(f"  source .venv/bin/activate")
    print("")
    trace_dir = os.path.join(script_dir, "traces")
    print("AFTER THE RUN — save transcript and record the result:")
    if args.agent_system == "claude-code":
        print(f"  Save transcript: cp ~/.claude/projects/<dir>/<uuid>.jsonl {trace_dir}/{session_id}.jsonl")
    elif args.agent_system == "codex":
        print(f"  Save transcript: cp ~/.codex/sessions/YYYY/MM/DD/<rollout>.jsonl {trace_dir}/{session_id}.jsonl")
    elif args.agent_system == "cursor":
        print(f"  Save transcript: copy the exported markdown conversation to {trace_dir}/{session_id}_cursor.jsonl")
    else:
        print(f"  Save transcript to {trace_dir}/{session_id}.jsonl")
    print(f"  {record_cmd}")
    print("")
    print("=" * 60)
    print(prompt)
