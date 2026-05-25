#!/usr/bin/env python3
"""Disk Image Utilities — mount, analyze, and extract from disk images.

Provides wrappers for common disk image operations including:
- E01/VMDK/VHD mounting via dissect
- Partition table analysis
- File system browsing and extraction
- 7z-based extraction (for APK/ZIP/backup files)
- Registry hive extraction from disk images
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple
import subprocess
import shutil
import os
import json
from pathlib import Path


@dataclass
class DiskResult:
    command: str = ""
    return_code: int = 0
    stdout: str = ""
    stderr: str = ""
    parsed: list = field(default_factory=list)
    files: List[str] = field(default_factory=list)
    error: str = ""

    @property
    def success(self) -> bool:
        return self.return_code == 0

    def to_dict(self) -> dict:
        return {
            "command": self.command,
            "return_code": self.return_code,
            "stdout_lines": len(self.stdout.splitlines()) if self.stdout else 0,
            "files_found": len(self.files),
            "parsed_count": len(self.parsed),
            "error": self.error or self.stderr[:500],
        }


# ── 7z extraction ──


def extract_7z(
    archive: str,
    output_dir: str = ".",
    password: str = "",
    timeout: int = 300,
) -> DiskResult:
    """Extract files from archive using 7-Zip.

    Supports: 7z, ZIP, RAR, TAR, GZ, APK, E01 (raw), VMDK (raw), VHD, BAK, etc.

    Args:
        archive: Path to archive file
        output_dir: Output directory
        password: Optional password for encrypted archives
        timeout: Command timeout
    """
    exe = shutil.which("7z")
    if not exe:
        return DiskResult(
            command="7z",
            return_code=-127,
            error="7z not found. Install: scoop install 7zip",
        )

    output_dir = os.path.abspath(output_dir)
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    cmd = [exe, "x", f"-o{output_dir}", "-y", archive]
    if password:
        cmd.insert(2, f"-p{password}")

    result = DiskResult(command=" ".join(cmd))

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

        # List extracted files
        if result.success:
            result.files = _list_extracted(output_dir)
    except subprocess.TimeoutExpired:
        result.return_code = -2
        result.error = f"Timeout after {timeout}s"
    except FileNotFoundError:
        result.return_code = -127
        result.error = "7z not found"
    except Exception as e:
        result.return_code = -3
        result.error = str(e)

    return result


def list_archive(archive: str, timeout: int = 60) -> DiskResult:
    """List contents of an archive without extracting."""
    exe = shutil.which("7z")
    if not exe:
        return DiskResult(command="7z", return_code=-127, error="7z not found")

    cmd = [exe, "l", archive]
    result = DiskResult(command=" ".join(cmd))

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
    except Exception as e:
        result.error = str(e)

    return result


def _list_extracted(dir_path: str, max_files: int = 500) -> List[str]:
    """Walk directory and return relative file paths."""
    files = []
    base = Path(dir_path)
    try:
        for path in base.rglob("*"):
            if path.is_file():
                rel = str(path.relative_to(base))
                files.append(rel)
                if len(files) >= max_files:
                    files.append(f"... (truncated)")
                    break
    except OSError:
        pass
    return files


# ── E01 / VMDK / VHD mounting via dissect ──


def get_disk_info(image_path: str, timeout: int = 60) -> DiskResult:
    """Get disk image info using dissect.

    Args:
        image_path: Path to E01/VMDK/VHD/raw image
        timeout: Command timeout

    Returns:
        DiskResult with stdout containing partition table and filesystem info
    """
    result = DiskResult(command=f"e01_reader info {image_path}")

    try:
        from tools.forensics.e01_reader import open_image, get_volumes, open_filesystem
        fh = open_image(image_path)
        size = fh.seek(0, 2)
        fh.seek(0)

        info_lines = [
            f"Image: {image_path}",
            f"Size: {size:,} bytes ({size / (1024**3):.2f} GB)",
        ]

        volumes = get_volumes(fh)
        if volumes:
            info_lines.append(f"Partitions: {len(volumes)}")
            for i, vol in enumerate(volumes):
                vol_size = getattr(vol, "size", 0)
                vol_offset = getattr(vol, "offset", 0)
                vol_type = getattr(vol, "type_str", getattr(vol, "type_name", "?"))
                info_lines.append(
                    f"  [{i}] offset={vol_offset} size={vol_size:,} type={vol_type}"
                )
        else:
            info_lines.append("No partition table, raw filesystem")

        result.stdout = "\n".join(info_lines)
        result.return_code = 0
    except Exception as e:
        result.error = str(e)
        result.return_code = -1

    return result


def list_disk_files(
    image_path: str,
    path: str = "/",
    recursive: bool = True,
    max_depth: int = 3,
) -> DiskResult:
    """List files in a disk image.

    Args:
        image_path: Path to E01/VMDK/VHD image
        path: Path within the image to list
        recursive: Whether to recurse into subdirectories
        max_depth: Maximum recursion depth

    Returns:
        DiskResult with .files containing file paths within the image
    """
    result = DiskResult(command=f"list_disk_files {image_path}:{path}")
    try:
        from tools.forensics.e01_reader import open_image, open_filesystem, _list_dir
        fh = open_image(image_path)
        fs, fs_type, _ = open_filesystem(fh)

        if not fs:
            result.error = "Could not open filesystem on image"
            result.return_code = -1
            return result

        path = path.replace("\\", "/")
        if not path.startswith("/"):
            path = "/" + path

        entry = fs.get(path)
        if entry.is_dir():
            files = []
            _collect_files(fs, path, files, recursive, max_depth, 0)
            result.files = files
        else:
            result.files = [path]

        result.stdout = f"Filesystem: {fs_type}\nFiles found: {len(result.files)}"
        result.return_code = 0
    except Exception as e:
        result.error = str(e)
        result.return_code = -1

    return result


def _collect_files(fs, path, files_list, recursive, max_depth, depth):
    """Recursively collect file paths from fs (helper)."""
    try:
        entry = fs.get(path)
        for child_name in entry.listdir():
            child_path = path.rstrip("/") + "/" + child_name
            try:
                child_entry = fs.get(child_path)
                if child_entry.is_dir():
                    if recursive and depth < max_depth:
                        _collect_files(fs, child_path, files_list, recursive, max_depth, depth + 1)
                else:
                    files_list.append(child_path)
            except Exception:
                files_list.append(child_path)
    except Exception:
        pass


def extract_file_from_disk(
    image_path: str,
    file_path: str,
    output_path: str,
    partition: Optional[int] = None,
) -> DiskResult:
    """Extract a single file from a disk image.

    Args:
        image_path: Path to E01/VMDK/VHD image
        file_path: Path within the image to extract
        output_path: Local output path
        partition: Partition index to use (None = auto)

    Returns:
        DiskResult indicating success/failure
    """
    result = DiskResult(command=f"extract {image_path}:{file_path} -> {output_path}")
    try:
        from tools.forensics.e01_reader import open_image, open_filesystem, cmd_extract

        fh = open_image(image_path)
        fs, _, _ = open_filesystem(fh, partition)

        if not fs:
            result.error = "Could not open filesystem on image"
            result.return_code = -1
            return result

        file_path = file_path.replace("\\", "/")
        entry = fs.get(file_path)

        os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)

        if hasattr(entry, "open"):
            f = entry.open()
        else:
            f = entry

        with open(output_path, "wb") as out:
            while True:
                chunk = f.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)

        final_size = os.path.getsize(output_path)
        result.stdout = f"Extracted: {file_path} -> {output_path} ({final_size:,} bytes)"
        result.return_code = 0
    except Exception as e:
        result.error = str(e)
        result.return_code = -1

    return result


# ── Registry extraction from disk ──


def extract_registry_hive(
    image_path: str,
    hive_name: str,
    output_dir: str = ".",
    partition: Optional[int] = None,
) -> DiskResult:
    """Extract Windows registry hives from a disk image.

    Common hives: SYSTEM, SOFTWARE, SAM, SECURITY, NTUSER.DAT, USRCLASS.DAT

    Args:
        image_path: Path to disk image
        hive_name: Name of registry hive to find and extract
        output_dir: Output directory
        partition: Optional partition index

    Returns:
        DiskResult with file paths
    """
    result = DiskResult(command=f"extract_registry {hive_name} from {image_path}")

    common_paths = [
        "Windows/System32/config",
        "WINDOWS/system32/config",
        "Windows/System32/config/RegBack",
        "Users",
        "Documents and Settings",
    ]

    if hive_name.upper() in ("NTUSER.DAT", "USRCLASS.DAT"):
        # User hives are under user profiles
        common_paths = [
            "Users/*/" + hive_name.upper(),
            "Documents and Settings/*/" + hive_name.upper(),
        ]

    try:
        from tools.forensics.e01_reader import open_image, open_filesystem
        fh = open_image(image_path)
        fs, fs_type, _ = open_filesystem(fh, partition)

        if not fs:
            result.error = "Could not open filesystem"
            result.return_code = -1
            return result

        found_files = []
        for base_path in common_paths:
            try:
                # Try direct path
                direct_path = base_path + "/" + hive_name if "*" not in base_path else None
                if direct_path:
                    try:
                        entry = fs.get(direct_path)
                        if not entry.is_dir():
                            found_files.append(direct_path)
                    except Exception:
                        pass

                # Also search
                try:
                    base_entry = fs.get(base_path)
                    for child in base_entry.listdir():
                        if child.upper() == hive_name.upper():
                            found_files.append(base_path + "/" + child)
                except Exception:
                    pass
            except Exception:
                continue

        if found_files:
            output_dir = os.path.abspath(output_dir)
            Path(output_dir).mkdir(parents=True, exist_ok=True)

            for found in found_files:
                local_path = os.path.join(output_dir, os.path.basename(found) or hive_name)
                entry = fs.get(found)
                if hasattr(entry, "open"):
                    f = entry.open()
                    with open(local_path, "wb") as out:
                        while True:
                            chunk = f.read(1024 * 1024)
                            if not chunk:
                                break
                            out.write(chunk)
                    result.files.append(local_path)

            result.stdout = f"Extracted {len(result.files)} registry hives: {result.files}"
            result.return_code = 0
        else:
            result.error = f"Hive '{hive_name}' not found in common locations"
            result.return_code = -1
    except Exception as e:
        result.error = str(e)
        result.return_code = -1

    return result


# ── File type detection ──


def detect_file_type(file_path: str, timeout: int = 10) -> DiskResult:
    """Detect file type using file command or magic bytes.

    Args:
        file_path: Path to file
        timeout: Command timeout

    Returns:
        DiskResult with file type in stdout
    """
    result = DiskResult(command=f"detect_file_type {file_path}")

    # Try 'file' command first (available via scoop/git)
    exe = shutil.which("file")
    if exe:
        try:
            proc = subprocess.run(
                [exe, file_path],
                capture_output=True,
                timeout=timeout,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            result.stdout = proc.stdout.strip()
            result.return_code = proc.returncode
            return result
        except Exception:
            pass

    # Fallback: magic byte detection
    try:
        with open(file_path, "rb") as f:
            header = f.read(16)

        magics = {
            b"\x89PNG\r\n\x1a\n": "PNG image",
            b"\xff\xd8\xff": "JPEG image",
            b"GIF8": "GIF image",
            b"BM": "BMP image",
            b"MZ": "PE executable / DOS MZ",
            b"\x7fELF": "ELF executable",
            b"PK\x03\x04": "ZIP archive",
            b"Rar!\x1a\x07": "RAR archive",
            b"\x1f\x8b": "GZIP archive",
            b"\xfd7zXZ": "XZ archive",
            b"BZh": "BZIP2 archive",
            b"SQLite format 3": "SQLite database",
            b"\x00\x00\x01\x00": "Windows icon (ICO)",
            b"EVF\x09\x0d\x0a\xff\x00": "EWF / E01 image",
            b"KDM": "VMDK disk image",
            b"%PDF": "PDF document",
            b"\xd0\xcf\x11\xe0": "MS Office document (OLE)",
            b"PK\x07\x08": "Empty ZIP archive",
        }
        for magic, desc in magics.items():
            if header.startswith(magic):
                result.stdout = desc
                result.return_code = 0
                break

        if not result.stdout:
            result.stdout = f"Unknown type (header: {header[:8].hex()})"
    except Exception as e:
        result.error = str(e)

    return result


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Disk image utilities")
    sub = parser.add_subparsers(dest="cmd")

    p_extract = sub.add_parser("extract", help="Extract archive with 7z")
    p_extract.add_argument("archive")
    p_extract.add_argument("-o", "--output", default=".", help="Output directory")
    p_extract.add_argument("-p", "--password", default="", help="Password")

    p_info = sub.add_parser("info", help="Get disk image info")
    p_info.add_argument("image")

    p_list = sub.add_parser("list", help="List files in disk image")
    p_list.add_argument("image")
    p_list.add_argument("path", nargs="?", default="/")
    p_list.add_argument("--depth", type=int, default=3)

    p_file = sub.add_parser("extract-file", help="Extract file from disk image")
    p_file.add_argument("image")
    p_file.add_argument("src")
    p_file.add_argument("dst")

    p_type = sub.add_parser("type", help="Detect file type")
    p_type.add_argument("file")

    args = parser.parse_args()

    if args.cmd == "extract":
        r = extract_7z(args.archive, args.output, args.password)
        print(r.stdout or r.error)
        for f in r.files[:50]:
            print(f"  {f}")
    elif args.cmd == "info":
        r = get_disk_info(args.image)
        print(r.stdout or r.error)
    elif args.cmd == "list":
        r = list_disk_files(args.image, args.path, max_depth=args.depth)
        print(r.stdout or r.error)
        for f in r.files[:100]:
            print(f"  {f}")
    elif args.cmd == "extract-file":
        r = extract_file_from_disk(args.image, args.src, args.dst)
        print(r.stdout or r.error)
    elif args.cmd == "type":
        r = detect_file_type(args.file)
        print(r.stdout or r.error)
    else:
        parser.print_help()
        sys.exit(1)
