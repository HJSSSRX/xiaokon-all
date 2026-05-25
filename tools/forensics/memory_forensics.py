#!/usr/bin/env python3
"""Memory Forensics Wrapper — thin Python interface over volatility3 CLI.

Provides convenience functions for common memory forensics commands,
structured output parsing, and integration with the tool pool.

Usage:
    from tools.forensics.memory_forensics import (
        vol3_info, vol3_pslist, vol3_netscan, vol3_filescan,
        vol3_malfind, vol3_dumpfiles, vol3_cmdline, vol3_registry,
        Vol3Result, run_vol3
    )

    info = vol3_info("memory.dmp")
    procs = vol3_pslist("memory.dmp")
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
import json
import re
import subprocess
import shutil
import sys
from pathlib import Path


@dataclass
class Vol3Result:
    command: str = ""
    return_code: int = 0
    stdout: str = ""
    stderr: str = ""
    parsed: list = field(default_factory=list)
    error: str = ""

    @property
    def success(self) -> bool:
        return self.return_code == 0

    def to_dict(self) -> dict:
        return {
            "command": self.command,
            "return_code": self.return_code,
            "stdout_lines": len(self.stdout.splitlines()) if self.stdout else 0,
            "parsed_count": len(self.parsed),
            "error": self.error or self.stderr[:500],
        }


def _find_vol3() -> Optional[str]:
    """Find volatility3 executable."""
    # Try 'vol3' alias first (common)
    exe = shutil.which("vol3")
    if exe:
        return exe
    exe = shutil.which("volatility3")
    if exe:
        return exe
    # Try Python module
    for candidate in ["vol", "volatility3", "vol3"]:
        found = shutil.which(candidate)
        if found:
            return found
    return None


def run_vol3(
    args: List[str],
    timeout: int = 120,
    memory_file: Optional[str] = None,
) -> Vol3Result:
    """Run an arbitrary volatility3 command.

    Args:
        args: Arguments to pass to volatility3 (e.g. ["windows.info"])
        timeout: Command timeout in seconds
        memory_file: If provided, prepend -f <file> to args

    Returns:
        Vol3Result with stdout, stderr, and parsed output.
    """
    exe = _find_vol3()
    if not exe:
        return Vol3Result(
            command=" ".join(args),
            return_code=-1,
            error="volatility3 not found in PATH. Install: pip install volatility3",
        )

    cmd = [sys.executable, "-m", "volatility3"] if exe in (sys.executable, "python") else [exe]
    if memory_file:
        cmd.extend(["-f", memory_file])
    cmd.extend(args)

    result = Vol3Result(command=" ".join(cmd))

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        result.return_code = proc.returncode
        result.stdout = proc.stdout
        result.stderr = proc.stderr
    except subprocess.TimeoutExpired:
        result.return_code = -2
        result.error = f"Timeout after {timeout}s"
    except Exception as e:
        result.return_code = -3
        result.error = str(e)

    return result


# ── Common volatility3 plugin wrappers ──


def vol3_info(memory_file: str, timeout: int = 60) -> Vol3Result:
    """Get basic system info from memory dump."""
    return run_vol3(["windows.info"], memory_file=memory_file, timeout=timeout)


def vol3_pslist(memory_file: str, timeout: int = 60) -> Vol3Result:
    """List processes in memory dump.

    Returns parsed list of processes with PID, PPID, name.
    """
    result = run_vol3(["windows.pslist"], memory_file=memory_file, timeout=timeout)
    result.parsed = _parse_pslist(result.stdout)
    return result


def vol3_psscan(memory_file: str, timeout: int = 60) -> Vol3Result:
    """Scan for hidden/terminated processes (carve from memory)."""
    return run_vol3(["windows.psscan"], memory_file=memory_file, timeout=timeout)


def vol3_pstree(memory_file: str, timeout: int = 60) -> Vol3Result:
    """Process tree (parent-child relationships)."""
    return run_vol3(["windows.pstree"], memory_file=memory_file, timeout=timeout)


def vol3_netscan(memory_file: str, timeout: int = 60) -> Vol3Result:
    """Network connections and sockets.

    Returns parsed list of connections.
    """
    result = run_vol3(["windows.netscan"], memory_file=memory_file, timeout=timeout)
    result.parsed = _parse_netscan(result.stdout)
    return result


def vol3_filescan(memory_file: str, timeout: int = 120) -> Vol3Result:
    """Scan for file objects in memory.

    Returns parsed list of {offset, path, size}.
    """
    result = run_vol3(["windows.filescan"], memory_file=memory_file, timeout=timeout)
    result.parsed = _parse_filescan(result.stdout)
    return result


def vol3_dumpfiles(
    memory_file: str,
    offset: str = "",
    pid: str = "",
    output_dir: str = ".",
    timeout: int = 120,
) -> Vol3Result:
    """Dump file from memory by offset."""
    args = ["windows.dumpfiles"]
    if offset:
        args.extend(["--virtaddr", offset])
    if pid:
        args.extend(["--pid", pid])
    args.extend(["--dump-dir", output_dir])
    return run_vol3(args, memory_file=memory_file, timeout=timeout)


def vol3_malfind(
    memory_file: str,
    pid: str = "",
    timeout: int = 120,
) -> Vol3Result:
    """Detect hidden/injected code (Malfind).

    Returns parsed list of malware findings.
    """
    args = ["windows.malfind"]
    if pid:
        args.extend(["--pid", pid])
    result = run_vol3(args, memory_file=memory_file, timeout=timeout)
    result.parsed = _parse_malfind(result.stdout)
    return result


def vol3_cmdline(memory_file: str, timeout: int = 60) -> Vol3Result:
    """Extract process command lines."""
    return run_vol3(["windows.cmdline"], memory_file=memory_file, timeout=timeout)


def vol3_registry_hivelist(memory_file: str, timeout: int = 60) -> Vol3Result:
    """List registry hives in memory."""
    return run_vol3(["windows.registry.hivelist"], memory_file=memory_file, timeout=timeout)


def vol3_registry_printkey(
    memory_file: str,
    key: str,
    timeout: int = 60,
) -> Vol3Result:
    """Print registry key contents."""
    return run_vol3(
        ["windows.registry.printkey", "--key", key],
        memory_file=memory_file,
        timeout=timeout,
    )


def vol3_handles(
    memory_file: str,
    pid: str = "",
    timeout: int = 60,
) -> Vol3Result:
    """List open handles for a process."""
    args = ["windows.handles"]
    if pid:
        args.extend(["--pid", pid])
    return run_vol3(args, memory_file=memory_file, timeout=timeout)


def vol3_dlllist(memory_file: str, pid: str = "", timeout: int = 60) -> Vol3Result:
    """List loaded DLLs for a process."""
    args = ["windows.dlllist"]
    if pid:
        args.extend(["--pid", pid])
    return run_vol3(args, memory_file=memory_file, timeout=timeout)


# ── Linux memory forensics ──


def vol3_linux_pslist(memory_file: str, timeout: int = 60) -> Vol3Result:
    """Linux process listing."""
    return run_vol3(["linux.pslist"], memory_file=memory_file, timeout=timeout)


def vol3_linux_bash(memory_file: str, timeout: int = 60) -> Vol3Result:
    """Linux bash history recovery."""
    return run_vol3(["linux.bash"], memory_file=memory_file, timeout=timeout)


def vol3_linux_proc_maps(memory_file: str, timeout: int = 60) -> Vol3Result:
    """Linux process memory maps."""
    return run_vol3(["linux.proc.Maps"], memory_file=memory_file, timeout=timeout)


# ── Output parsers ──


def _parse_pslist(stdout: str) -> List[Dict[str, Any]]:
    """Parse pslist output into structured records."""
    results = []
    if not stdout:
        return results

    lines = stdout.splitlines()
    header_found = False
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if not header_found and ("PID" in line or "Offset" in line):
            header_found = True
            continue
        if not header_found:
            continue

        parts = line.split()
        if len(parts) >= 3:
            entry = {"raw": line}
            # Typical format: PID  PPID  ImageFileName  Offset(V)
            try:
                entry["pid"] = int(parts[0])
            except ValueError:
                entry["offset"] = parts[0]
                if len(parts) >= 4:
                    try:
                        entry["pid"] = int(parts[1])
                        entry["ppid"] = int(parts[2])
                        entry["name"] = parts[3]
                    except (ValueError, IndexError):
                        pass
                    results.append(entry)
                continue
            try:
                entry["ppid"] = int(parts[1])
            except (ValueError, IndexError):
                pass
            if len(parts) >= 3:
                entry["name"] = parts[2]
            results.append(entry)

    return results


def _parse_netscan(stdout: str) -> List[Dict[str, Any]]:
    """Parse netscan output into structured records."""
    results = []
    if not stdout:
        return results

    lines = stdout.splitlines()
    for line in lines:
        line = line.strip()
        if not line or "Offset" in line or "Proto" in line:
            continue
        parts = line.split()
        if len(parts) >= 5:
            entry = {
                "raw": line,
                "proto": parts[1] if len(parts) > 1 else "",
                "local_addr": parts[2] if len(parts) > 2 else "",
                "foreign_addr": parts[3] if len(parts) > 3 else "",
                "state": parts[4] if len(parts) > 4 else "",
            }
            # Try to extract PID if present
            if len(parts) > 5:
                try:
                    entry["pid"] = int(parts[5])
                except ValueError:
                    pass
            # Try to extract owner if present
            if len(parts) > 6:
                entry["owner"] = parts[6]
            results.append(entry)

    return results


def _parse_filescan(stdout: str) -> List[Dict[str, Any]]:
    """Parse filescan output."""
    results = []
    if not stdout:
        return results

    for line in stdout.splitlines():
        line = line.strip()
        if not line or "Offset" in line:
            continue
        entry = {"raw": line}

        # Format: Offset  Size  Path
        # Or:      Offset(V)  Ptr  Hnd  Access  Name
        parts = line.split()
        if len(parts) >= 2:
            entry["offset"] = parts[0]
            # Try finding path (last element with \ or /)
            for part in reversed(parts):
                if "\\" in part or "/" in part or "." in part:
                    entry["path"] = " ".join(
                        parts[parts.index(part) :]
                        if part in parts
                        else [parts[-1]]
                    )
                    break
            if len(parts) >= 3:
                try:
                    entry["size"] = int(parts[1])
                except ValueError:
                    pass
        results.append(entry)

    return results


def _parse_malfind(stdout: str) -> List[Dict[str, Any]]:
    """Parse malfind output for suspicious findings."""
    results = []
    if not stdout:
        return results

    current = None
    lines = stdout.splitlines()
    for line in lines:
        line = line.strip()
        if not line:
            if current and current.get("addresses"):
                results.append(current)
            current = None
            continue

        if "PID" in line and "Process" in line:
            if current and current.get("addresses"):
                results.append(current)
            current = {"raw_sections": [line], "addresses": [], "hex": []}
        elif current is not None:
            current["raw_sections"].append(line)
            if re.match(r"^0x[0-9a-fA-F]+", line):
                current["addresses"].append(line.split()[0] if line.split() else line)
            if "PAGE_EXECUTE" in line:
                current["protection"] = "PAGE_EXECUTE"
            if "MZ" in line or "\\x" in line:
                current["hex"].append(line)

    if current and current.get("addresses"):
        results.append(current)

    return results


# ── Bulk analysis ──


def vol3_full_scan(
    memory_file: str,
    output_dir: str = ".",
    timeout_per_plugin: int = 120,
) -> Dict[str, Vol3Result]:
    """Run a comprehensive set of volatility plugins.

    Returns dict of {plugin_name: Vol3Result}.
    """
    plugins = {
        "info": lambda: vol3_info(memory_file, timeout=timeout_per_plugin),
        "pslist": lambda: vol3_pslist(memory_file, timeout=timeout_per_plugin),
        "netscan": lambda: vol3_netscan(memory_file, timeout=timeout_per_plugin),
        "filescan": lambda: vol3_filescan(memory_file, timeout=timeout_per_plugin),
        "cmdline": lambda: vol3_cmdline(memory_file, timeout=timeout_per_plugin),
        "malfind": lambda: vol3_malfind(memory_file, timeout=timeout_per_plugin),
        "pstree": lambda: vol3_pstree(memory_file, timeout=timeout_per_plugin),
        "hivelist": lambda: vol3_registry_hivelist(memory_file, timeout=timeout_per_plugin),
    }

    results = {}
    for name, fn in plugins.items():
        try:
            results[name] = fn()
        except Exception as e:
            results[name] = Vol3Result(command=name, error=str(e))

    # Save report
    report_path = Path(output_dir) / f"vol3_scan_{Path(memory_file).stem}.json"
    report = {k: v.to_dict() for k, v in results.items()}
    try:
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    except OSError:
        pass

    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Volatility3 memory forensics wrapper")
    parser.add_argument("memory_file", help="Path to memory dump")
    parser.add_argument(
        "--plugin",
        default="info",
        choices=[
            "info", "pslist", "psscan", "pstree", "netscan", "filescan",
            "malfind", "cmdline", "hivelist", "handles", "dlllist",
            "linux_pslist", "linux_bash", "full",
        ],
        help="Plugin to run (default: info)",
    )
    parser.add_argument("--pid", default="", help="Filter by PID")
    parser.add_argument("--key", default="", help="Registry key path")
    parser.add_argument("--output-dir", default=".", help="Output directory")
    parser.add_argument("--timeout", type=int, default=120, help="Timeout per plugin")
    args = parser.parse_args()

    memory_file = args.memory_file

    plugin_map = {
        "info": lambda: vol3_info(memory_file, timeout=args.timeout),
        "pslist": lambda: vol3_pslist(memory_file, timeout=args.timeout),
        "psscan": lambda: vol3_psscan(memory_file, timeout=args.timeout),
        "pstree": lambda: vol3_pstree(memory_file, timeout=args.timeout),
        "netscan": lambda: vol3_netscan(memory_file, timeout=args.timeout),
        "filescan": lambda: vol3_filescan(memory_file, timeout=args.timeout),
        "malfind": lambda: vol3_malfind(memory_file, pid=args.pid, timeout=args.timeout),
        "cmdline": lambda: vol3_cmdline(memory_file, timeout=args.timeout),
        "hivelist": lambda: vol3_registry_hivelist(memory_file, timeout=args.timeout),
        "handles": lambda: vol3_handles(memory_file, pid=args.pid, timeout=args.timeout),
        "dlllist": lambda: vol3_dlllist(memory_file, pid=args.pid, timeout=args.timeout),
        "linux_pslist": lambda: vol3_linux_pslist(memory_file, timeout=args.timeout),
        "linux_bash": lambda: vol3_linux_bash(memory_file, timeout=args.timeout),
        "full": lambda: vol3_full_scan(memory_file, output_dir=args.output_dir, timeout_per_plugin=args.timeout),
    }

    fn = plugin_map.get(args.plugin)
    if fn:
        result = fn()
        if isinstance(result, dict):
            for name, r in result.items():
                status = "OK" if r.success else "FAIL"
                print(f"[{status}] {name}: {r.parsed_count if hasattr(r, 'parsed_count') else ''}")
        else:
            if result.success:
                print(result.stdout[:5000] if result.stdout else "(no output)")
                if result.parsed:
                    print(f"\n--- Parsed {len(result.parsed)} entries ---")
                    for entry in result.parsed[:20]:
                        print(entry)
            else:
                print(f"ERROR: {result.error or result.stderr}")
    else:
        print(f"Unknown plugin: {args.plugin}")
