#!/usr/bin/env python3
"""
E01 Reader — CLI tool to browse and extract files from E01/VMDK images.
Uses Fox-IT dissect library. Requires Python 3.10+.

Usage:
    python e01_reader.py info <image>
    python e01_reader.py ls <image> <path> [--recursive] [--depth N]
    python e01_reader.py cat <image> <path>
    python e01_reader.py extract <image> <path> <output>
    python e01_reader.py hash <image> <path>
    python e01_reader.py search <image> <pattern> [--path /]
    python e01_reader.py partitions <image>
"""
import sys
import os
import hashlib
import argparse
import fnmatch
from pathlib import PureWindowsPath, PurePosixPath


def open_image(image_path):
    """Open E01/raw/VMDK image and return a seekable file-like stream."""
    ext = os.path.splitext(image_path)[1].lower()
    if ext == '.e01':
        from dissect.evidence.ewf import EWF
        ewf = EWF(open(image_path, 'rb'))
        stream = ewf.open()
        stream._ewf_ref = ewf  # prevent GC
        return stream
    elif ext == '.vmdk':
        try:
            from dissect.hypervisor.disk.vmdk import VMDK
            vmdk = VMDK(open(image_path, 'rb'))
            return vmdk
        except Exception:
            return open(image_path, 'rb')
    else:
        return open(image_path, 'rb')


def get_volumes(fh):
    """Get all filesystem volumes from a disk image."""
    from dissect.volume import disk
    try:
        d = disk.Disk(fh)
        return list(d.partitions)
    except Exception:
        return []


def open_filesystem(fh, partition_index=None):
    """Try to open a filesystem from the image. Returns (fs, fs_type) tuple."""
    from dissect.volume import disk

    volumes = []
    try:
        d = disk.Disk(fh)
        volumes = list(d.partitions)
    except Exception:
        pass

    if volumes:
        targets = [volumes[partition_index]] if partition_index is not None else volumes
        for vol in targets:
            try:
                vol_fh = vol.open()
            except Exception:
                continue
            fs, fs_type = _try_open_fs(vol_fh)
            if fs:
                return fs, fs_type, vol
    else:
        fs, fs_type = _try_open_fs(fh)
        if fs:
            return fs, fs_type, None

    return None, None, None


class NtfsWrapper:
    """Wrapper around dissect.ntfs.NTFS to provide a uniform FS interface."""
    def __init__(self, ntfs_obj):
        self._ntfs = ntfs_obj

    def get(self, path):
        """Get MftRecord for a path like /Users/Desktop/file.txt"""
        path = path.replace('\\', '/').strip('/')
        record = self._ntfs.mft.root
        if not path or path == '.':
            return MftRecordWrapper(record)
        parts = path.split('/')
        for part in parts:
            found = False
            for idx_entry in record.iterdir():
                try:
                    child = idx_entry.dereference()
                    if child.filename and child.filename.lower() == part.lower():
                        record = child
                        found = True
                        break
                except Exception:
                    continue
            if not found:
                raise FileNotFoundError(f"Path not found: {path} (failed at '{part}')")
        return MftRecordWrapper(record)


class MftRecordWrapper:
    """Wrapper around MftRecord for uniform access."""
    def __init__(self, record):
        self._record = record

    def is_dir(self):
        return self._record.is_dir()

    @property
    def size(self):
        try:
            return self._record.size
        except Exception:
            try:
                return self._record.data().dataruns_size
            except Exception:
                return 0

    @property
    def name(self):
        return self._record.filename or ''

    def listdir(self):
        """Return list of (name, MftRecordWrapper) for directory entries."""
        seen = set()
        results = []
        for idx_entry in self._record.iterdir():
            try:
                child = idx_entry.dereference()
                fn = child.filename
                if fn and fn not in seen and fn != '.':
                    seen.add(fn)
                    results.append(fn)
            except Exception:
                continue
        return results

    def open(self):
        """Open file for reading."""
        return self._record.open()


def _try_open_fs(fh):
    """Try different filesystem parsers."""
    # NTFS
    try:
        from dissect.ntfs import NTFS
        ntfs = NTFS(fh=fh)
        _ = ntfs.mft.root  # verify it works
        return NtfsWrapper(ntfs), 'NTFS'
    except Exception:
        pass
    # EXT
    try:
        from dissect.extfs import ExtFilesystem
        ext = ExtFilesystem(fh)
        return ext, 'EXT'
    except Exception:
        pass
    # FAT
    try:
        from dissect.fat import FatFilesystem
        fat = FatFilesystem(fh)
        return fat, 'FAT'
    except Exception:
        pass
    return None, None


def cmd_info(args):
    """Show image info."""
    fh = open_image(args.image)
    size = fh.seek(0, 2)
    fh.seek(0)
    print(f"Image: {args.image}")
    print(f"Size:  {size:,} bytes ({size / (1024**3):.2f} GB)")

    volumes = get_volumes(fh)
    if volumes:
        print(f"Partitions: {len(volumes)}")
        for i, vol in enumerate(volumes):
            vol_size = getattr(vol, 'size', 0)
            vol_offset = getattr(vol, 'offset', 0)
            vol_type = getattr(vol, 'type_str', getattr(vol, 'type_name', '?'))
            try:
                fs, fs_type = _try_open_fs(vol.open())
            except Exception:
                fs, fs_type = None, None
            fs_info = fs_type if fs_type else "unknown"
            print(f"  [{i}] offset={vol_offset} size={vol_size:,} ({vol_size/(1024**3):.2f}GB) type={vol_type} fs={fs_info}")
    else:
        print("No partition table found, trying raw filesystem...")
        fs, fs_type = _try_open_fs(fh)
        if fs_type:
            print(f"  Filesystem: {fs_type}")
        else:
            print("  No recognized filesystem")


def cmd_partitions(args):
    """List partitions."""
    fh = open_image(args.image)
    volumes = get_volumes(fh)
    if not volumes:
        print("No partitions found.")
        return
    for i, vol in enumerate(volumes):
        vol_size = getattr(vol, 'size', 0)
        vol_type = getattr(vol, 'type_str', getattr(vol, 'type_name', '?'))
        try:
            fs, fs_type = _try_open_fs(vol.open())
        except Exception:
            fs, fs_type = None, None
        print(f"[{i}] size={vol_size:,} ({vol_size/(1024**3):.2f}GB) type={vol_type} fs={fs_type or 'unknown'}")


def cmd_ls(args):
    """List files in a directory."""
    fh = open_image(args.image)
    fs, fs_type, _ = open_filesystem(fh, getattr(args, 'partition', None))
    if not fs:
        print("ERROR: Cannot open filesystem", file=sys.stderr)
        sys.exit(1)

    path = args.path.replace('\\', '/')
    if not path.startswith('/'):
        path = '/' + path

    try:
        _list_dir(fs, path, args.recursive, args.depth, 0)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


def _list_dir(fs, path, recursive, max_depth, current_depth):
    """List directory contents."""
    try:
        entry = fs.get(path)
    except Exception as e:
        print(f"Cannot access {path}: {e}", file=sys.stderr)
        return

    if not entry.is_dir():
        _print_entry(path, entry)
        return

    for child_name in entry.listdir():
        child_path = path.rstrip('/') + '/' + child_name
        try:
            child_entry = fs.get(child_path)
            _print_entry(child_path, child_entry)
            if recursive and child_entry.is_dir() and current_depth < max_depth:
                _list_dir(fs, child_path, recursive, max_depth, current_depth + 1)
        except Exception as e:
            print(f"  [error: {child_path} - {e}]")


def _print_entry(path, entry):
    """Print a single file/dir entry."""
    try:
        is_dir = entry.is_dir()
        size = 0 if is_dir else entry.size
        entry_type = "DIR " if is_dir else "FILE"
        print(f"{entry_type}  {size:>12,}  {path}")
    except Exception:
        print(f"????  {'':>12}  {path}")


def cmd_cat(args):
    """Print file contents to stdout."""
    fh = open_image(args.image)
    fs, _, _ = open_filesystem(fh, getattr(args, 'partition', None))
    if not fs:
        print("ERROR: Cannot open filesystem", file=sys.stderr)
        sys.exit(1)

    path = args.path.replace('\\', '/')
    entry = fs.get(path)
    if entry.is_dir():
        print("ERROR: Target is a directory", file=sys.stderr)
        sys.exit(1)

    if hasattr(entry, 'open'):
        f = entry.open()
    else:
        f = entry

    data = f.read()
    if args.binary:
        sys.stdout.buffer.write(data)
    else:
        try:
            sys.stdout.write(data.decode('utf-8', errors='replace'))
        except Exception:
            sys.stdout.buffer.write(data)


def cmd_extract(args):
    """Extract a file from the image."""
    fh = open_image(args.image)
    fs, _, _ = open_filesystem(fh, getattr(args, 'partition', None))
    if not fs:
        print("ERROR: Cannot open filesystem", file=sys.stderr)
        sys.exit(1)

    path = args.path.replace('\\', '/')
    entry = fs.get(path)

    os.makedirs(os.path.dirname(os.path.abspath(args.output)) or '.', exist_ok=True)

    if hasattr(entry, 'open'):
        f = entry.open()
    else:
        f = entry

    with open(args.output, 'wb') as out:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)

    final_size = os.path.getsize(args.output)
    print(f"Extracted: {path} -> {args.output} ({final_size:,} bytes)")


def cmd_hash(args):
    """Calculate hash of a file in the image."""
    fh = open_image(args.image)
    fs, _, _ = open_filesystem(fh, getattr(args, 'partition', None))
    if not fs:
        print("ERROR: Cannot open filesystem", file=sys.stderr)
        sys.exit(1)

    path = args.path.replace('\\', '/')
    entry = fs.get(path)

    if hasattr(entry, 'open'):
        f = entry.open()
    else:
        f = entry

    h_sha256 = hashlib.sha256()
    h_md5 = hashlib.md5()
    h_sha1 = hashlib.sha1()
    total = 0
    while True:
        chunk = f.read(1024 * 1024)
        if not chunk:
            break
        h_sha256.update(chunk)
        h_md5.update(chunk)
        h_sha1.update(chunk)
        total += len(chunk)

    print(f"File:   {path}")
    print(f"Size:   {total:,} bytes")
    print(f"MD5:    {h_md5.hexdigest().upper()}")
    print(f"SHA1:   {h_sha1.hexdigest().upper()}")
    print(f"SHA256: {h_sha256.hexdigest().upper()}")


def cmd_search(args):
    """Search for files matching a pattern."""
    fh = open_image(args.image)
    fs, _, _ = open_filesystem(fh, getattr(args, 'partition', None))
    if not fs:
        print("ERROR: Cannot open filesystem", file=sys.stderr)
        sys.exit(1)

    start_path = (args.path or '/').replace('\\', '/')
    pattern = args.pattern.lower()
    count = 0

    def _search(path):
        nonlocal count
        try:
            entry = fs.get(path)
            if not entry.is_dir():
                return
            for child in entry.listdir():
                child_path = path.rstrip('/') + '/' + child
                if fnmatch.fnmatch(child.lower(), pattern):
                    try:
                        child_entry = fs.get(child_path)
                        _print_entry(child_path, child_entry)
                        count += 1
                        if count >= 200:
                            print(f"... (stopped at 200 results)")
                            return
                    except Exception:
                        print(f"FILE  {'?':>12}  {child_path}")
                        count += 1
                try:
                    child_entry = fs.get(child_path)
                    if child_entry.is_dir():
                        _search(child_path)
                except Exception:
                    pass
        except Exception:
            pass

    _search(start_path)
    print(f"\n{count} matches found.")


def main():
    parser = argparse.ArgumentParser(description='E01/VMDK image browser')
    parser.add_argument('-p', '--partition', type=int, default=None,
                        help='Partition index to use')
    sub = parser.add_subparsers(dest='command')

    p_info = sub.add_parser('info', help='Show image info')
    p_info.add_argument('image')

    p_parts = sub.add_parser('partitions', help='List partitions')
    p_parts.add_argument('image')

    p_ls = sub.add_parser('ls', help='List directory')
    p_ls.add_argument('image')
    p_ls.add_argument('path', nargs='?', default='/')
    p_ls.add_argument('-r', '--recursive', action='store_true')
    p_ls.add_argument('-d', '--depth', type=int, default=3)

    p_cat = sub.add_parser('cat', help='Print file contents')
    p_cat.add_argument('image')
    p_cat.add_argument('path')
    p_cat.add_argument('-b', '--binary', action='store_true')

    p_ext = sub.add_parser('extract', help='Extract file')
    p_ext.add_argument('image')
    p_ext.add_argument('path')
    p_ext.add_argument('output')

    p_hash = sub.add_parser('hash', help='Hash file')
    p_hash.add_argument('image')
    p_hash.add_argument('path')

    p_search = sub.add_parser('search', help='Search for files')
    p_search.add_argument('image')
    p_search.add_argument('pattern', help='Glob pattern, e.g. *.txt')
    p_search.add_argument('--path', default='/', help='Start path')

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    cmds = {
        'info': cmd_info, 'partitions': cmd_partitions, 'ls': cmd_ls,
        'cat': cmd_cat, 'extract': cmd_extract, 'hash': cmd_hash,
        'search': cmd_search,
    }
    cmds[args.command](args)


if __name__ == '__main__':
    main()
