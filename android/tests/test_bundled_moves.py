#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build gate for complete cost-plus-future policies and live ROM timing."""
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools/offline-moves'))
from verify_cost_runtime import main

if __name__=='__main__':
    main()
