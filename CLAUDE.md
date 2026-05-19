# AutoForensicAI

This is a digital forensics and security automation project powered by AI multi-agent coordination.

> **Coding principles**: Think before coding · Simplicity first · Surgical changes · Goal-driven execution

## Quick Start

When the user says **"小空自己动"**, read and follow the instructions in `prompts/main.md` to enter Main Designer mode.

## First-Time Setup

```powershell
.\install.ps1           # Install all tools (reads tools/manifest.yaml)
.\install.ps1 -Check    # Check status only
python tools\tool_status.py  # Query what's installed and where
```

## Project Structure

```
prompts/           — System prompts (main.md, role templates)
knowledge/
  solved/          — Verified solutions with searchable tags
  skills/          — Per-role skill files (techniques, tool usage)
  cards/           — Extracted knowledge cards from external sources
tools/
  cli.py           — Unified CLI entry point (hub, sync, kb, schedule, lint)
  manifest.yaml    — Tool manifest (single source of truth)
  tool_status.py   — Query tool availability + paths
  kb_search.py     — Knowledge base search
  collab/          — Collaboration package (hub server, sync, conflict resolution)
  collab_hub.py    — Backward-compat shim → tools/collab/
  collab_sync.py   — Backward-compat shim → tools/collab/
  core/            — Shared infrastructure (HTTP base, ID gen, YAML, cache, etc.)
  feeder/          — Knowledge ingestion from external sources
  e01_reader.py    — E01/VMDK image reader
```

## Key Rules

1. **Search before solving**: Run `python tools/kb_search.py --ask "{question}"` or `--tags` before starting any analysis
2. **CLI over MCP**: Use command-line tools directly (nmap, vol3, strings, tshark, sqlmap, etc.)
3. **Document everything**: Every session must produce a `knowledge/solved/*.md` file
4. **Coordinate via HTTP Hub**: Start `python tools/cli.py hub serve <case_dir> --port 8765` for multi-agent communication (v3 protocol)
5. **Consultant mode**: User can ask forensics/security questions anytime — search KB and answer from existing knowledge
6. **Tool paths**: Run `python tools/tool_status.py --find <tool>` to get exact paths for tools not in PATH

## AI Tag System

Use the AI Tag Engine for efficient context retrieval:

```python
from feeder import get_context_for_practice, get_context_for_learning, quick_search

# Get context for solving questions
context = get_context_for_practice("knowledge", {
    "domain": "computer",
    "tags": ["memory_forensics", "volatility"]
})

# Get learning path
path = get_context_for_learning("knowledge", "SQL注入")

# Quick search by tags
result = quick_search("knowledge", ["sql_injection", "php"])
```

## Knowledge Base Structure

```
knowledge/
├── sources/           # Track 1: Direct knowledge (articles, docs)
│   ├── articles/      # By domain (web, binary, forensics...)
│   ├── cheatsheets/   # Quick reference
│   └── _index.yaml
├── practice/          # Track 2: Learned from problems
│   ├── solved/        # Solved problems by competition
│   ├── patterns/      # Common solution patterns
│   └── _index.yaml
├── skills/            # Fusion layer: Skills from both tracks
│   ├── computer/      # By forensics domain
│   ├── mobile/
│   ├── network/
│   └── _index.yaml
└── _relations/        # Tag-based linking
    ├── tag_index.yaml
    └── tag_index_cache.json  # AI-optimized cache
```
