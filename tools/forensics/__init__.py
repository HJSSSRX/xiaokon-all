"""forensics module — shared E01/image I/O helpers.

Consolidated from duplicated open_e01/read_at patterns across
e01_string_search, e01_extract_dbs, e01_explore, e01_extract_key, e01_pass2.

Optional dependency: pyewf (libewf-python) for E01 image support.
"""


def _get_pyewf():
    """Lazy-import pyewf so the package is importable without it installed."""
    try:
        import pyewf
        return pyewf
    except ImportError:
        raise ImportError(
            "pyewf is required for E01 forensics. Install with: pip install libewf-python"
        )


def open_e01(image_path: str):
    """Open an E01 forensic image. Returns a pyewf handle."""
    pyewf = _get_pyewf()
    filenames = pyewf.glob(image_path)
    h = pyewf.handle()
    h.open(filenames)
    return h


def read_at(handle, offset: int, size: int) -> bytes:
    """Read bytes at a specific offset from an open pyewf handle."""
    handle.seek(offset)
    return handle.read(size)


# Lazy accessors for submodules (avoid heavy imports at package load)


def get_memory_forensics():
    """Return the memory_forensics module (lazy import)."""
    from . import memory_forensics
    return memory_forensics


def get_tool_wrappers():
    """Return the tool_wrappers module (lazy import)."""
    from . import tool_wrappers
    return tool_wrappers


def get_disk_utils():
    """Return the disk_utils module (lazy import)."""
    from . import disk_utils
    return disk_utils
