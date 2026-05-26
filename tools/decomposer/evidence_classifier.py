"""Evidence classifier: extension + magic bytes detection.

Reuses extension mapping pattern from smart_scheduler.py and adds
content-based magic byte detection for ambiguous file types.
"""

import os
from pathlib import Path
from typing import List

from tools.decomposer.models import EvidenceInfo

# Extension → detected_type (consistent with smart_scheduler.TaskType)
EXTENSION_TYPE_MAP = {
    # Memory
    ".dmp": "memory", ".mem": "memory", ".vmem": "memory",
    ".core": "memory", ".img": "memory",
    # Disk
    ".e01": "disk", ".vmdk": "disk", ".vhd": "disk", ".vhdx": "disk",
    ".raw": "disk", ".dd": "disk", ".aff": "disk", ".qcow2": "disk",
    # Network
    ".pcap": "network", ".pcapng": "network", ".cap": "network",
    # Mobile
    ".apk": "mobile", ".ipa": "mobile", ".ab": "mobile", ".tar": "mobile",
    # Binary/RE
    ".exe": "binary", ".dll": "binary", ".so": "binary", ".elf": "binary",
    ".sys": "binary", ".o": "binary",
    # Stego
    ".jpg": "stego", ".jpeg": "stego", ".png": "stego", ".bmp": "stego",
    ".gif": "stego", ".wav": "stego", ".mp3": "stego", ".mp4": "stego",
    # Crypto
    ".enc": "crypto", ".gpg": "crypto", ".hash": "crypto",
    # Logs
    ".evtx": "log", ".log": "log", ".txt": "log", ".csv": "log", ".tsv": "log",
    # Email
    ".eml": "misc", ".mbox": "misc", ".pst": "misc", ".ost": "misc",
    # Archives (not a forensic domain, but needs extraction)
    ".zip": "archive", ".rar": "archive", ".7z": "archive", ".gz": "archive",
    ".bz2": "archive", ".xz": "archive", ".tar.gz": "archive",
    # Generic — may need magic byte disambiguation
    ".bin": "unknown", ".dat": "unknown", ".file": "unknown",
}

ARCHIVE_EXTENSIONS = {".zip", ".rar", ".7z", ".gz", ".bz2", ".xz", ".tar.gz", ".tar"}
ENCRYPTED_EXTENSIONS = {".enc", ".gpg"}
MOUNT_EXTENSIONS = {".e01", ".vmdk", ".vhd", ".vhdx", ".qcow2", ".aff"}

# Magic byte signatures — first N bytes → detected_type
MAGIC_SIGNATURES = {
    # PE executables
    "4d5a": "binary",
    # ELF executables
    "7f454c46": "binary",
    # PCAP files
    "d4c3b2a1": "network",
    "a1b2c3d4": "network",
    "0a0d0d0a": "network",
    # ZIP-based (APK, IPA, DOCX, etc.)
    "504b0304": "archive",
    "504b0506": "archive",
    "504b0708": "archive",
    # RAR
    "52617221": "archive",
    # 7z
    "377abcaf": "archive",
    # GZ
    "1f8b": "archive",
    # BZ2
    "425a68": "archive",
    # EWF (E01)
    "45564609": "disk",
    # VMDK
    "4b444d": "disk",
    # SQLite
    "53514c69": "mobile",
    # JPEG
    "ffd8ff": "stego",
    # PNG
    "89504e47": "stego",
    # GIF
    "47494638": "stego",
    # BMP
    "424d": "stego",
    # WAV
    "52494646": "stego",
}


def _read_magic(filepath: str, n: int = 8) -> str:
    """Read first n bytes and return as lowercase hex string."""
    try:
        with open(filepath, "rb") as f:
            return f.read(n).hex()
    except (IOError, PermissionError):
        return ""


def _classify_by_magic(magic: str) -> str:
    """Match magic bytes against known signatures, longest match first."""
    for sig, ftype in sorted(MAGIC_SIGNATURES.items(), key=lambda x: -len(x[0])):
        if magic.startswith(sig):
            return ftype
    return "unknown"


def _classify_by_name(filename: str) -> str:
    """Classify by filename patterns when extension is ambiguous."""
    lower = filename.lower()
    if any(k in lower for k in ("memory", "memdump", "mem_dump", ".dmp", ".vmem")):
        return "memory"
    if any(k in lower for k in ("disk", "image", ".e01", ".vmdk", ".vhd")):
        return "disk"
    if any(k in lower for k in ("pcap", "capture", "network", "traffic")):
        return "network"
    if any(k in lower for k in ("mobile", "phone", "android", "ios", "backup")):
        return "mobile"
    if any(k in lower for k in ("malware", "suspicious", "trojan")):
        return "binary"
    return "unknown"


SKIP_DIRS = {"decomposition", ".git", "__pycache__", ".claude", "node_modules"}
SKIP_FILES = {"decomposition_report.md", "execution_plan.json", "tasks.json"}


def classify_evidence(
    evidence_dir: str, max_depth: int = 3, compute_hashes: bool = True,
    skip_dirs: set = None,
) -> List[EvidenceInfo]:
    """Walk evidence directory and classify every file.

    Uses extension mapping first, then magic bytes for ambiguous files,
    then filename heuristics as final fallback.

    Args:
        evidence_dir: Root directory containing evidence files.
        max_depth: Maximum directory recursion depth.
        compute_hashes: Whether to compute SHA256 hashes.
        skip_dirs: Additional directory names to skip.

    Returns:
        List of EvidenceInfo objects sorted by size descending.
    """
    if skip_dirs is None:
        skip_dirs = set()
    skip_dirs = SKIP_DIRS | skip_dirs

    evidence_dir = os.path.abspath(evidence_dir)
    result: List[EvidenceInfo] = []

    for root, dirs, files in os.walk(evidence_dir):
        # Exclude skip directories
        dirs[:] = [d for d in dirs if d not in skip_dirs]

        depth = root[len(evidence_dir):].count(os.sep)
        if depth > max_depth:
            dirs.clear()
            continue

        for filename in files:
            if filename in SKIP_FILES:
                continue

            filepath = os.path.join(root, filename)
            relpath = os.path.relpath(filepath, evidence_dir)

            try:
                st = os.stat(filepath)
            except OSError:
                continue

            ext = Path(filename).suffix.lower()
            double_ext = "".join(Path(filename).suffixes[-2:]).lower()

            # Primary: extension
            detected = EXTENSION_TYPE_MAP.get(double_ext) or EXTENSION_TYPE_MAP.get(ext, "unknown")

            magic = _read_magic(filepath)
            magic_type = _classify_by_magic(magic) if magic else "unknown"

            # Resolve conflicts: magic bytes win for unknown/ambiguous extensions
            if detected in ("unknown",):
                detected = magic_type
            elif magic_type != "unknown" and detected != magic_type:
                if detected == "archive" and magic_type in ("mobile", "binary"):
                    detected = magic_type

            # Fallback: filename heuristics
            if detected == "unknown":
                detected = _classify_by_name(filename)

            is_archive = ext in ARCHIVE_EXTENSIONS or double_ext in ARCHIVE_EXTENSIONS
            is_encrypted = ext in ENCRYPTED_EXTENSIONS
            mount_needed = ext in MOUNT_EXTENSIONS

            sha = ""
            if compute_hashes:
                try:
                    from tools.core.utils import compute_hash
                    sha = compute_hash(filepath)
                except ImportError:
                    import hashlib
                    try:
                        h = hashlib.sha256()
                        with open(filepath, "rb") as f:
                            for chunk in iter(lambda: f.read(65536), b""):
                                h.update(chunk)
                        sha = h.hexdigest()
                    except (IOError, PermissionError):
                        sha = ""

            result.append(EvidenceInfo(
                path=relpath,
                size_bytes=st.st_size,
                extension=ext,
                detected_type=detected,
                magic_bytes=magic[:16] if magic else "",
                mime_type="",
                sha256=sha,
                is_archive=is_archive,
                is_encrypted=is_encrypted,
                mount_required=mount_needed,
            ))

    result.sort(key=lambda e: e.size_bytes, reverse=True)
    return result


def summarize_evidence(evidence: List[EvidenceInfo]) -> dict:
    """Generate summary statistics for a list of evidence files."""
    by_type: dict = {}
    total_size = 0
    for e in evidence:
        by_type[e.detected_type] = by_type.get(e.detected_type, 0) + 1
        total_size += e.size_bytes

    return {
        "total_files": len(evidence),
        "total_size_bytes": total_size,
        "total_size_gb": round(total_size / (1024 ** 3), 2),
        "by_type": by_type,
        "archives": [e.path for e in evidence if e.is_archive],
        "encrypted": [e.path for e in evidence if e.is_encrypted],
        "mountable": [e.path for e in evidence if e.mount_required],
        "types_detected": list(by_type.keys()),
    }
