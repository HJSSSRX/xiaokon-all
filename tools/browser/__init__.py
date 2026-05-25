"""browser module — abstract browser backend and static backend implementation.

Provides:
- BrowserBackend: abstract base class
- BrowserResult: normalized output dataclass
- StaticBackend: requests + BeautifulSoup implementation
"""

from .base import BrowserBackend, BrowserResult
from .static_backend import StaticBackend

__all__ = ["BrowserBackend", "BrowserResult", "StaticBackend"]
