#!/usr/bin/env python3
"""AutoForensicAI — unified CLI entry point.

Usage:
  python -m tools.cli hub serve <case_dir> [--port PORT] [--bind BIND]
  python -m tools.cli sync <subcommand> [args...]
  python -m tools.cli schedule --case-dir DIR [--auto-generate] [--execute ID] [--progress]
  python -m tools.cli generate-roles [--out-dir DIR] [--kb-base DIR]
  python -m tools.cli captain [--hub URL] [--case DIR] [--watch N] [--json]
  python -m tools.cli kb build [--dir DIR] [--check] [--dry-run]
  python -m tools.cli kb search <query> [--case-dir DIR]
  python -m tools.cli import <yaml_file> [--hub URL] [--role ROLE] [--type TYPE]
  python -m tools.cli lint [--case DIR] [--cat CAT] [--fix] [--hub URL] [--json]
"""

import sys

GROUPS = {
    "hub": "tools.collab.hub_server",
    "sync": "tools.collab.sync_cli",
    "schedule": "tools.smart_scheduler",
    "generate-roles": "tools.generate_role_prompts_v5",
    "captain": "tools.captain",
    "kb": None,       # sub-routed below
    "analytics": None,  # sub-routed below
    "decompose": None,  # sub-routed below
    "executor": None,  # sub-routed below
    "import": "tools.hub.import_yaml",
    "lint": "tools.answer_format_lint",
}


def _print_usage():
    print("AutoForensicAI — unified CLI")
    print()
    print("Groups:")
    print("  hub serve <case>            Start collaboration hub server")
    print("  sync <cmd> [args]           Collaboration sync (post, status, git-*, lan-*, sync)")
    print("  schedule --case-dir <dir>   Smart task scheduling")
    print("  generate-roles [opts]       Generate role prompt files")
    print("  captain [opts]              Captain console dashboard")
    print("  kb build [opts]             Build knowledge base index")
    print("  kb search <query> [opts]    Search knowledge base")
    print("  analytics mine [opts]       Mine association rules from KB")
    print("  analytics report [opts]     Generate association rule report")
    print("  analytics recommend [opts]  Recommend tools/tags for evidence context")
    print("  decompose --dir DIR [opts]  Decompose challenge into sub-goal DAG")
    print("  executor start --plan <path> Start focused execution session")
    print("  executor status [opts]       Show execution progress")
    print("  executor next [opts]         Print context for next ready sub-goal")
    print("  executor boost [opts]        Weak model boost — 6-step amplification pipeline")
    print("  import <yaml> [opts]        Import YAML to hub")
    print("  lint [opts]                 Answer format lint")
    print()
    print("Run 'python -m tools.cli <group> --help' for details.")


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        _print_usage()
        return

    group = sys.argv[1]

    # kb has sub-groups
    if group == "kb":
        if len(sys.argv) < 3:
            print("Usage: forensic kb <build|search> [opts]")
            return
        kb_cmd = sys.argv[2]
        if kb_cmd == "build":
            sys.argv = ["kb_build"] + sys.argv[3:]
            from tools.kb.build_index import main as m
        elif kb_cmd == "search":
            sys.argv = ["kb_search"] + sys.argv[3:]
            from tools.kb.search import main as m
        else:
            print(f"Unknown kb command: {kb_cmd}")
            return
        m()
        return

    # decompose has sub-groups
    if group == "decompose":
        sys.argv = ["decompose"] + sys.argv[2:]
        from tools.decomposer.cli import main as m
        m()
        return

    # executor has sub-groups
    if group == "executor":
        sys.argv = ["executor"] + sys.argv[2:]
        from tools.decomposer.session_cli import main as m
        m()
        return

    # analytics has sub-groups
    if group == "analytics":
        if len(sys.argv) < 3:
            print("Usage: forensic analytics <mine|report> [opts]")
            return
        sub = sys.argv[2]
        sys.argv = ["analytics"] + sys.argv[2:]
        from tools.analytics.cli import main as m
        m()
        return

    module_path = GROUPS.get(group)
    if module_path is None:
        print(f"Unknown group: {group}")
        _print_usage()
        return

    # Forward remaining argv to the target module's main()
    sys.argv = [group] + sys.argv[2:]
    import importlib
    mod = importlib.import_module(module_path)
    mod.main()


if __name__ == "__main__":
    main()
# test
