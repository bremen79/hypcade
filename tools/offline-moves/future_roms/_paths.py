# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared source locations for package imports and direct diagnostic commands."""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
CORE = HERE.parent
REPO = CORE.parents[1]
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))


def source_path(name):
    """Resolve an optional helper locally, or a shared production source."""
    local = HERE / name
    return local if local.exists() else CORE / name
