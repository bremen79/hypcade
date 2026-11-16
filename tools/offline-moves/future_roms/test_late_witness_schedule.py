#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Reject ambiguous or unverifiable prerequisites for composed schedules."""

if __package__:
    from ._paths import CORE, HERE, REPO, source_path
else:
    from _paths import CORE, HERE, REPO, source_path

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from future_roms import late_witness_schedule as schedule


class WitnessScheduleTest(unittest.TestCase):
    def test_repeated_context_is_rejected_before_native_build(self):
        source = (schedule.ROOT/'rom_routes.c').read_text()
        anchor = dict(scene=8, step=6, control=16, source_cycle=10, delay=100)
        with self.assertRaisesRegex(ValueError, 'Repeated context'):
            schedule.guarded(source, [anchor, dict(anchor, source_cycle=20)])

    def test_prior_verification_and_physical_trace_are_required(self):
        with TemporaryDirectory() as folder:
            folder = Path(folder)
            path = folder/'report.json'
            path.write_text(json.dumps(dict(verified=False)))
            with self.assertRaisesRegex(ValueError, 'not independently verified'):
                schedule.load(path)
            trace = folder/'route.trace'
            trace.write_text('physical evidence')
            row = dict(verified=True, anchors=[], trace_sha256=hashlib.sha256(trace.read_bytes()).hexdigest())
            path.write_text(json.dumps(row))
            self.assertEqual(schedule.load(path), [])
            trace.write_text('changed')
            with self.assertRaisesRegex(ValueError, 'physical trace changed'):
                schedule.load(path)

    def test_legacy_schedule_retains_exact_checkpoint(self):
        with TemporaryDirectory() as folder:
            folder = Path(folder)
            trace = folder/'route.trace'
            trace.write_text('evidence')
            row = dict(verified=True, selected_event=dict(source_cycle=123),
                trace_sha256=hashlib.sha256(trace.read_bytes()).hexdigest())
            path = folder/'report.json'
            path.write_text(json.dumps(row))
            (folder/'input-timing.txt').write_text('HYPCADE_ROM_TIMING_V1\n38 0 4 500\n')
            self.assertEqual(schedule.load(path), [dict(scene=38, step=0, control=4, delay=500, source_cycle=123)])


if __name__ == '__main__':
    unittest.main()
