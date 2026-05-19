"""Constants shared across hub modules."""

import re
import threading

ROLE_PREFIX = {
    "computer_analyst": "C",
    "mobile_analyst": "M",
    "server_analyst": "S",
    "binary_analyst": "B",
    "main_designer": "D",
}

ROLE_TO_CATEGORY = {
    "computer_analyst": "computer_forensics",
    "mobile_analyst": "mobile_forensics",
    "server_analyst": "server_forensics",
    "binary_analyst": "binary_forensics",
    "internet_analyst": "internet_forensics",
}

FILE_WHITELIST = re.compile(
    r"^(role_prompt_\w+\.md|shared/[\w_-]+\.(yaml|md|jsonl)|[A-Z][A-Z0-9_]+\.md|README\.md|import_[\w_]+\.py)$"
)

_LOCK = threading.Lock()
_HUB_STARTED_AT = None

NEED_STATUS = ("open", "claimed", "fulfilled", "abandoned")
NEED_CONFIDENCE_5 = (
    "platform_confirmed",
    "self_verified_db",
    "cross_source_high",
    "single_source_high",
    "gui_observed",
    "placeholder",
)
NEED_CONFIDENCE_LEGACY = ("high", "medium", "low")
