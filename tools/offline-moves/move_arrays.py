#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Share identical immutable move, rule and index arrays across ROM revisions."""
import re


def deduplicate(source):
    owners = {}
    aliases = dict(re.findall(r'^#define (\w+) (\w+)\s*$', source, re.M))
    def array(match):
        kind, name, body = match.groups()
        key = (kind, re.sub(r'\s+', '', body))
        if key not in owners:
            owners[key] = name
            return match[0]
        aliases[name] = owners[key]
        return '#define %s %s' % (name, owners[key])
    source = re.sub(r'static const (ArcadeRomMove|ArcadeRomRule|ArcadeEuroRule|uint16_t) (\w+)\[\] = \{(.*?)\};',
                    array, source, flags=re.S)
    return source, aliases
