"""pcap module — shared packet analysis helpers.

Consolidated from duplicated ip_str/read_pcap patterns across
pcap_analysis_2024szb, pcap_analysis_pass2, pcap_pass3, pcap_pass4,
and the weevely/pass5 sub-modules.

Optional dependency: dpkt for packet capture parsing.
"""

import socket


def _get_dpkt():
    """Lazy-import dpkt so the package is importable without it installed."""
    try:
        import dpkt
        return dpkt
    except ImportError:
        raise ImportError(
            "dpkt is required for pcap analysis. Install with: pip install dpkt"
        )


def ip_str(packed) -> str:
    """Convert packed IP address bytes to a dotted string."""
    return socket.inet_ntoa(packed)


def read_pcapng(path: str):
    """Yield (timestamp, buffer) tuples from a pcapng file.

    Falls back to legacy pcap if pcapng read fails.
    """
    dpkt = _get_dpkt()
    with open(path, 'rb') as f:
        try:
            reader = dpkt.pcapng.Reader(f)
        except Exception:
            f.seek(0)
            reader = dpkt.pcap.Reader(f)
        for ts, buf in reader:
            yield ts, buf


def read_pcap(path: str):
    """Yield (timestamp, buffer) tuples from a legacy pcap file."""
    dpkt = _get_dpkt()
    with open(path, 'rb') as f:
        for ts, buf in dpkt.pcap.Reader(f):
            yield ts, buf


def get_pass5():
    """Return the pass5 module (lazy import)."""
    from . import pass5
    return pass5


def get_weevely():
    """Return the weevely module (lazy import)."""
    from . import weevely
    return weevely
