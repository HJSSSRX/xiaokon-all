#!/usr/bin/env python3
"""Thin Python wrappers over external forensic CLI tools.

Provides convenience functions with consistent interfaces, structured output
parsing, and fallback detection for the most commonly used forensic tools.

Usage:
    from tools.forensics.tool_wrappers import (
        run_strings, run_exiftool, run_binwalk, run_foremost,
        run_sqlite3_query, run_floss,
    )
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
import subprocess
import shutil
import json
import re
from pathlib import Path


@dataclass
class ToolResult:
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
            "stdout_len": len(self.stdout) if self.stdout else 0,
            "parsed_count": len(self.parsed),
            "error": self.error or self.stderr[:500],
        }


def _run(cmd: List[str], timeout: int = 60) -> ToolResult:
    """Execute a command and return ToolResult."""
    result = ToolResult(command=" ".join(cmd))
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
    except FileNotFoundError:
        result.return_code = -127
        result.error = f"Tool not found: {cmd[0]}"
    except Exception as e:
        result.return_code = -3
        result.error = str(e)
    return result


# ── strings ──


def run_strings(
    target: str,
    min_length: int = 4,
    encoding: str = "both",  # "ascii", "unicode", "both"
    max_output: int = 100000,
    timeout: int = 60,
) -> ToolResult:
    """Extract printable strings from binary/memory file.

    Falls back to Python implementation if sysinternals strings not found.

    Args:
        target: Path to file
        min_length: Minimum string length
        encoding: "ascii" for ASCII, "unicode" for UTF-16LE, "both" for both
        max_output: Max chars to return
        timeout: Command timeout
    """
    exe = shutil.which("strings")
    if exe:
        cmd = [exe]
        if encoding == "unicode" or encoding == "both":
            cmd.append("-u")
        cmd.extend(["-n", str(min_length), target])
        result = _run(cmd, timeout=timeout)
        if result.stdout and len(result.stdout) > max_output:
            result.stdout = result.stdout[:max_output] + "\n...(truncated)"
        return result

    # Fallback: Python strings extraction
    return _strings_python(target, min_length, encoding, max_output)


def _strings_python(
    target: str,
    min_length: int = 4,
    encoding: str = "both",
    max_output: int = 100000,
) -> ToolResult:
    """Pure Python strings extraction fallback."""
    result = ToolResult(command=f"python_strings -n {min_length} {encoding} {target}")
    try:
        with open(target, "rb") as f:
            data = f.read()
    except Exception as e:
        result.error = str(e)
        return result

    strings_set = set()
    current = bytearray()

    for byte in data:
        if 32 <= byte < 127:  # ASCII printable
            current.append(byte)
        elif encoding in ("unicode", "both") and len(current) == 0:
            current.append(byte)
        else:
            if len(current) >= min_length:
                try:
                    strings_set.add(current.decode("ascii", errors="replace"))
                except Exception:
                    pass
            current = bytearray()

    if len(current) >= min_length:
        try:
            strings_set.add(current.decode("ascii", errors="replace"))
        except Exception:
            pass

    # Also try UTF-16LE if requested
    if encoding in ("unicode", "both"):
        for i in range(0, len(data) - 1, 2):
            try:
                char = data[i : i + 2].decode("utf-16-le", errors="ignore")
                if len(char) == 1 and char.isprintable():
                    pass  # Too short for individual chars
            except Exception:
                pass

    output = "\n".join(sorted(strings_set))
    if len(output) > max_output:
        output = output[:max_output] + "\n...(truncated)"
    result.stdout = output
    result.return_code = 0
    return result


# ── exiftool ──


def run_exiftool(
    target: str,
    timeout: int = 30,
    json_output: bool = True,
) -> ToolResult:
    """Extract metadata from file using ExifTool.

    Args:
        target: Path to file or directory
        timeout: Command timeout
        json_output: If True, parse JSON output into parsed list
    """
    exe = shutil.which("exiftool")
    if not exe:
        return ToolResult(
            command="exiftool",
            return_code=-127,
            error="exiftool not found. Install: scoop install exiftool",
        )

    cmd = [exe]
    if json_output:
        cmd.append("-j")
    cmd.append(target)

    result = _run(cmd, timeout=timeout)

    if json_output and result.success and result.stdout:
        try:
            result.parsed = json.loads(result.stdout)
        except json.JSONDecodeError:
            pass

    return result


# ── binwalk ──


def run_binwalk(
    target: str,
    extract: bool = False,
    extract_dir: str = "",
    signature: bool = True,
    opcodes: bool = False,
    entropy: bool = False,
    timeout: int = 120,
) -> ToolResult:
    """Analyze and extract embedded files using binwalk.

    Args:
        target: Path to file
        extract: If True, extract found files (-e)
        extract_dir: Optional output directory for extraction
        signature: Look for file signatures (default)
        opcodes: Look for CPU opcodes (-A)
        entropy: Entropy analysis (-E)
        timeout: Command timeout
    """
    exe = shutil.which("binwalk")
    if not exe:
        return ToolResult(
            command="binwalk",
            return_code=-127,
            error="binwalk not found. Install: pip install binwalk or WSL: apt install binwalk",
        )

    cmd = [exe]
    if signature:
        pass  # default
    if extract:
        cmd.append("-e")
        cmd.append("-M")  # matryoshka mode
    if extract_dir:
        cmd.extend(["-C", extract_dir])
    if opcodes:
        cmd.append("-A")
    if entropy:
        cmd.append("-E")
    cmd.append(target)

    return _run(cmd, timeout=timeout)


# ── foremost ──


def run_foremost(
    target: str,
    output_dir: str = "foremost_output",
    file_types: str = "all",
    timeout: int = 300,
) -> ToolResult:
    """File carving using foremost.

    Args:
        target: Path to disk image or raw data file
        output_dir: Output directory for carved files
        file_types: Comma-separated list or "all"
        timeout: Command timeout
    """
    exe = shutil.which("foremost")
    if not exe:
        return ToolResult(
            command="foremost",
            return_code=-127,
            error="foremost not found. Install via WSL: apt install foremost",
        )

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    cmd = [exe, "-t", file_types, "-i", target, "-o", output_dir]
    return _run(cmd, timeout=timeout)


# ── sqlite3 ──


def run_sqlite3_query(
    db_path: str,
    query: str = "",
    tables_only: bool = False,
    dump_schema: bool = False,
    timeout: int = 30,
) -> ToolResult:
    """Query SQLite databases via CLI.

    Args:
        db_path: Path to SQLite database file
        query: SQL query to execute
        tables_only: If True, list all tables
        dump_schema: If True, dump database schema
        timeout: Command timeout
    """
    exe = shutil.which("sqlite3")
    if not exe:
        return ToolResult(
            command="sqlite3",
            return_code=-127,
            error="sqlite3 CLI not found. Install: scoop install sqlite",
        )

    if tables_only:
        sql = ".tables"
    elif dump_schema:
        sql = ".schema"
    elif query:
        sql = query
    else:
        return ToolResult(
            command="sqlite3",
            return_code=-1,
            error="No query specified. Use tables_only=True, dump_schema=True, or pass a query.",
        )

    cmd = [exe, db_path, sql]
    return _run(cmd, timeout=timeout)


# ── floss (FireEye Labs Obfuscated String Solver) ──


def run_floss(
    target: str,
    quiet: bool = True,
    timeout: int = 120,
) -> ToolResult:
    """Extract obfuscated strings from binary using FLOSS.

    Args:
        target: Path to PE/ELF/Mach-O binary
        quiet: Suppress verbose output
        timeout: Command timeout
    """
    exe = shutil.which("floss")
    if not exe:
        return ToolResult(
            command="floss",
            return_code=-127,
            error="FLOSS not found. Install: pip install flare-floss",
        )

    cmd = [exe]
    if quiet:
        cmd.append("-q")
    cmd.append(target)

    return _run(cmd, timeout=timeout)


# ── chainsaw (Windows event log analysis) ──


def run_chainsaw(
    evtx_dir: str,
    sigma_rules_dir: str = "",
    output_format: str = "json",
    timeout: int = 120,
) -> ToolResult:
    """Analyze Windows EVTX logs with Chainsaw.

    Args:
        evtx_dir: Directory containing .evtx files
        sigma_rules_dir: Optional path to Sigma rules
        output_format: "json" or "ascii"
        timeout: Command timeout
    """
    exe = shutil.which("chainsaw")
    if not exe:
        return ToolResult(
            command="chainsaw",
            return_code=-127,
            error="chainsaw not found. Download from: https://github.com/WithSecureLabs/chainsaw/releases",
        )

    cmd = [exe, "hunt", evtx_dir]
    if sigma_rules_dir:
        cmd.extend(["--sigma", sigma_rules_dir])
    cmd.extend(["--output", output_format])

    return _run(cmd, timeout=timeout)


# ── nmap ──


def run_nmap(
    target: str,
    ports: str = "",
    scan_type: str = "sV",  # sS=syn, sT=connect, sV=version, sC=default scripts
    extra_args: Optional[List[str]] = None,
    timeout: int = 300,
) -> ToolResult:
    """Run nmap scan with parsed output.

    Args:
        target: IP/hostname or CIDR range
        ports: Port specification (e.g. "1-1000", "80,443")
        scan_type: Scan flags without dash (e.g. "sV", "sS", "sC", "A")
        extra_args: Additional nmap arguments
        timeout: Command timeout
    """
    exe = shutil.which("nmap")
    if not exe:
        return ToolResult(
            command="nmap",
            return_code=-127,
            error="nmap not found. Install: scoop install nmap",
        )

    cmd = [exe]
    # Build scan flags
    flags = ""
    for char in scan_type:
        flags += f"-{char} "
    cmd.extend(flags.split())
    if ports:
        cmd.extend(["-p", ports])
    if extra_args:
        cmd.extend(extra_args)
    cmd.append(target)

    result = _run(cmd, timeout=timeout)
    result.parsed = _parse_nmap(result.stdout)
    return result


def _parse_nmap(stdout: str) -> List[Dict[str, Any]]:
    """Parse nmap output into structured records."""
    results = []
    current_host = None
    lines = stdout.splitlines()

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # New host line: "Nmap scan report for HOST"
        if line.startswith("Nmap scan report for"):
            host = line.split("for ")[-1].strip()
            current_host = {"host": host, "ports": []}
            results.append(current_host)

        # Port line: "PORT   STATE   SERVICE   VERSION"
        elif current_host is not None and re.match(r"^\d+/", line):
            parts = line.split()
            if len(parts) >= 3:
                port_info = {
                    "port": parts[0],
                    "state": parts[1],
                    "service": parts[2],
                }
                if len(parts) > 3:
                    port_info["version"] = " ".join(parts[3:])
                current_host["ports"].append(port_info)

    return results


# ── tshark ──


def run_tshark(
    pcap_file: str,
    display_filter: str = "",
    fields: str = "",
    timeout: int = 120,
) -> ToolResult:
    """Run tshark with common filters.

    Args:
        pcap_file: Path to .pcap/.pcapng file
        display_filter: Wireshark display filter (e.g. "http.request")
        fields: Comma-separated field names for -T fields output
        timeout: Command timeout
    """
    exe = shutil.which("tshark")
    if not exe:
        return ToolResult(
            command="tshark",
            return_code=-127,
            error="tshark not found. Install: scoop install wireshark",
        )

    cmd = [exe, "-r", pcap_file]
    if display_filter:
        cmd.extend(["-Y", display_filter])
    if fields:
        cmd.extend(["-T", "fields", "-e"] + fields.split(","))
    # Limit output for large pcaps
    cmd.extend(["-c", "10000"])

    return _run(cmd, timeout=timeout)


def run_tshark_conversations(pcap_file: str, timeout: int = 60) -> ToolResult:
    """Show IP conversation summary."""
    exe = shutil.which("tshark")
    if not exe:
        return ToolResult(command="tshark", return_code=-127, error="tshark not found")
    cmd = [exe, "-r", pcap_file, "-q", "-z", "conv,ip"]
    return _run(cmd, timeout=timeout)


def run_tshark_protocol_hierarchy(pcap_file: str, timeout: int = 60) -> ToolResult:
    """Show protocol hierarchy statistics."""
    exe = shutil.which("tshark")
    if not exe:
        return ToolResult(command="tshark", return_code=-127, error="tshark not found")
    cmd = [exe, "-r", pcap_file, "-q", "-z", "io,phs"]
    return _run(cmd, timeout=timeout)


def run_tshark_http_objects(pcap_file: str, output_dir: str = ".", timeout: int = 60) -> ToolResult:
    """Export HTTP objects from pcap."""
    exe = shutil.which("tshark")
    if not exe:
        return ToolResult(command="tshark", return_code=-127, error="tshark not found")
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    cmd = [exe, "-r", pcap_file, "--export-objects", f"http,{output_dir}"]
    return _run(cmd, timeout=timeout)


def run_tshark_follow_stream(
    pcap_file: str, stream_index: int, timeout: int = 60
) -> ToolResult:
    """Follow a specific TCP stream."""
    exe = shutil.which("tshark")
    if not exe:
        return ToolResult(command="tshark", return_code=-127, error="tshark not found")
    cmd = [exe, "-r", pcap_file, "-q", "-z", f"follow,tcp,ascii,{stream_index}"]
    return _run(cmd, timeout=timeout)


# ── hashcat / john ──


def run_hashcat(
    hash_file: str,
    hash_mode: int = 0,
    attack_mode: int = 0,
    wordlist: str = "",
    rule: str = "",
    timeout: int = 300,
) -> ToolResult:
    """Run hashcat for password cracking.

    Args:
        hash_file: Path to file with hashes
        hash_mode: Hashcat hash mode number
        attack_mode: 0=straight, 1=combination, 3=bruteforce, 6=hybrid, etc.
        wordlist: Path to wordlist file
        rule: Path to rule file
        timeout: Command timeout
    """
    exe = shutil.which("hashcat")
    if not exe:
        return ToolResult(
            command="hashcat",
            return_code=-127,
            error="hashcat not found. Install: scoop install hashcat",
        )

    cmd = [exe, "-m", str(hash_mode), "-a", str(attack_mode)]
    if rule:
        cmd.extend(["-r", rule])
    cmd.append(hash_file)
    if wordlist:
        cmd.append(wordlist)

    return _run(cmd, timeout=timeout)


def run_zip2john(zip_file: str, output_file: str = "", timeout: int = 30) -> ToolResult:
    """Extract hash from ZIP for John the Ripper."""
    exe = shutil.which("zip2john")
    if not exe:
        return ToolResult(command="zip2john", return_code=-127, error="zip2john not found. Install: scoop install john-the-ripper")
    cmd = [exe, zip_file]
    result = _run(cmd, timeout=timeout)
    if output_file and result.success:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(result.stdout)
    return result


# ── steghide ──


def run_steghide_extract(
    stego_file: str,
    password: str = "",
    output_file: str = "",
    timeout: int = 30,
) -> ToolResult:
    """Extract hidden data from stego file using steghide.

    Args:
        stego_file: Path to JPEG/BMP with stego data
        password: Password (empty string = no password)
        output_file: Output path for extracted data
        timeout: Command timeout
    """
    exe = shutil.which("steghide")
    if not exe:
        return ToolResult(
            command="steghide",
            return_code=-127,
            error="steghide not found. Install via WSL: apt install steghide",
        )

    cmd = [exe, "extract", "-sf", stego_file]
    if password:
        cmd.extend(["-p", password])
    if output_file:
        cmd.extend(["-xf", output_file])
    # Force non-interactive
    if not password:
        cmd.extend(["-p", ""])

    return _run(cmd, timeout=timeout)


# ── zsteg ──


def run_zsteg(
    target: str,
    all_methods: bool = True,
    timeout: int = 60,
) -> ToolResult:
    """Detect LSB steganography in PNG/BMP.

    Args:
        target: Path to PNG or BMP file
        all_methods: If True, use -a flag for all tests
        timeout: Command timeout
    """
    exe = shutil.which("zsteg")
    if not exe:
        return ToolResult(
            command="zsteg",
            return_code=-127,
            error="zsteg not found. Install via WSL: gem install zsteg",
        )

    cmd = [exe]
    if all_methods:
        cmd.append("-a")
    cmd.append(target)

    return _run(cmd, timeout=timeout)


# ── sleuthkit wrappers ──


def run_fls(
    image: str,
    inode: str = "",
    recursive: bool = False,
    output_dir: str = "",
    timeout: int = 60,
) -> ToolResult:
    """List files in filesystem image (Sleuth Kit)."""
    exe = shutil.which("fls")
    if not exe:
        return ToolResult(command="fls", return_code=-127, error="fls not found. Install: scoop install sleuthkit (extras bucket)")
    cmd = [exe]
    if recursive:
        cmd.append("-r")
    if inode:
        cmd.append(inode)
    if output_dir:
        cmd.extend(["-m", output_dir])
    cmd.append(image)
    return _run(cmd, timeout=timeout)


def run_icat(
    image: str,
    inode: str,
    output_file: str = "",
    timeout: int = 60,
) -> ToolResult:
    """Extract file by inode from filesystem image (Sleuth Kit)."""
    exe = shutil.which("icat")
    if not exe:
        return ToolResult(command="icat", return_code=-127, error="icat not found. Install: scoop install sleuthkit")
    cmd = [exe, image, inode]
    result = _run(cmd, timeout=timeout)
    if output_file and result.success and result.stdout:
        Path(output_file).parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(result.stdout)
    return result


# ── Convenience: run any tool by name ──


def run_external_tool(
    tool_name: str,
    args: List[str],
    timeout: int = 60,
    wsl: bool = False,
) -> ToolResult:
    """Generic wrapper for any external CLI tool.

    Args:
        tool_name: Tool executable name
        args: Command arguments (list)
        timeout: Command timeout
        wsl: If True, run through WSL

    Returns:
        ToolResult
    """
    if wsl:
        cmd = ["wsl", "--", "bash", "-lc", f"{tool_name} {' '.join(args)}"]
    else:
        exe = shutil.which(tool_name)
        if not exe:
            return ToolResult(
                command=tool_name,
                return_code=-127,
                error=f"Tool '{tool_name}' not found in PATH",
            )
        cmd = [exe] + args

    return _run(cmd, timeout=timeout)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="External forensic tool wrappers")
    sub = parser.add_subparsers(dest="cmd")

    p_strings = sub.add_parser("strings", help="Extract printable strings")
    p_strings.add_argument("target")
    p_strings.add_argument("-n", type=int, default=4, help="Minimum string length")

    p_exiftool = sub.add_parser("exiftool", help="Extract metadata")
    p_exiftool.add_argument("target")

    p_binwalk = sub.add_parser("binwalk", help="Analyze embedded files")
    p_binwalk.add_argument("target")
    p_binwalk.add_argument("-e", action="store_true", help="Extract")

    p_nmap = sub.add_parser("nmap", help="Network scan")
    p_nmap.add_argument("target")
    p_nmap.add_argument("-p", dest="ports", default="", help="Port range")

    p_tshark = sub.add_parser("tshark", help="Packet analysis")
    p_tshark.add_argument("pcap")
    p_tshark.add_argument("-Y", dest="filter", default="", help="Display filter")

    args = parser.parse_args()

    if args.cmd == "strings":
        r = run_strings(args.target, min_length=args.n)
    elif args.cmd == "exiftool":
        r = run_exiftool(args.target)
    elif args.cmd == "binwalk":
        r = run_binwalk(args.target, extract=args.e)
    elif args.cmd == "nmap":
        r = run_nmap(args.target, ports=args.ports)
    elif args.cmd == "tshark":
        r = run_tshark(args.pcap, display_filter=args.filter)
    else:
        parser.print_help()
        import sys
        sys.exit(1)

    if r.success:
        print(r.stdout[:10000] if r.stdout else "(no output)")
        if r.parsed:
            print(f"\n--- Parsed {len(r.parsed)} entries ---")
    else:
        print(f"ERROR: {r.error or r.stderr[:500]}")
