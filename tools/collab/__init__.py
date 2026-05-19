"""Collaboration package — hub server + sync + conflict resolution + progressive sync."""

# Hub constants
from .hub_constants import (
    ROLE_PREFIX,
    ROLE_TO_CATEGORY,
    FILE_WHITELIST,
    _LOCK,
    _HUB_STARTED_AT,
    NEED_STATUS,
    NEED_CONFIDENCE_5,
    NEED_CONFIDENCE_LEGACY,
)

# Hub IDs
from .hub_ids import next_finding_id, normalize_confidence

# Hub handler
from .hub_handler import Handler

# Hub server
from .hub_server import get_local_ips, init_shared_files, cmd_serve

# Hub CLI
from .hub_cli import main as hub_main

# Conflict resolution
from .conflict import detect_duplicates, resolve_duplicate, compare_versions

# Git sync
from .git_sync import git_run, sync_git_file, cmd_git_init, cmd_git_push, cmd_git_pull

# LAN sync
from .lan_sync import (
    SyncHandler,
    sync_lan_file,
    get_last_sync_time,
    update_sync_time,
    cmd_lan_serve,
    cmd_lan_pull,
    cmd_lan_push,
)

# Progressive sync
from .progressive import SYNC_PRIORITIES, progressive_sync

# Sync CLI
from .sync_cli import (
    cmd_post,
    cmd_status,
    cmd_answers,
    cmd_detect_duplicates,
    cmd_resolve_conflict,
    cmd_version_compare,
    cmd_sync,
    main as sync_main,
)
