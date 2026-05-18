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
  manifest.yaml    — Tool manifest (single source of truth)
  tool_status.py   — Query tool availability + paths
  kb_search.py     — Knowledge base search
  collab_hub.py    — HTTP Hub server for multi-role coordination (v3)
  collab_sync.py   — Cross-machine collaboration (Git + LAN, legacy v2)
  e01_reader.py    — E01/VMDK image reader
```

## Key Rules

1. **Search before solving**: Run `python tools/kb_search.py --ask "{question}"` or `--tags` before starting any analysis
2. **CLI over MCP**: Use command-line tools directly (nmap, vol3, strings, tshark, sqlmap, etc.)
3. **Document everything**: Every session must produce a `knowledge/solved/*.md` file
4. **Coordinate via HTTP Hub**: Start `python tools/collab_hub.py serve <case_dir> --port 8765` for multi-agent communication (v3 protocol)
5. **Consultant mode**: User can ask forensics/security questions anytime — search KB and answer from existing knowledge
6. **Tool paths**: Run `python tools/tool_status.py --find <tool>` to get exact paths for tools not in PATH
