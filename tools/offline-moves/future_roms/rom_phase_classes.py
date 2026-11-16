#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Finite refresh classes for substituting released polls for accepted waits.

This is a conditional arithmetic contract, not an emulator or a reachability
proof. The caller must establish an unchanged polling regime, accepted wait
iteration, path to the selector, and absence (or normalization) of interrupts.
All costs are instruction-fetch counts (M1) and Z80 T states, obtained from ROM
loop contracts. No screen-frame timing offsets are involved.
"""
from dataclasses import dataclass
from math import gcd


@dataclass(frozen=True)
class LoopClasses:
    poll_m1: int
    poll_cycles: int
    wait_m1: int
    wait_cycles: int
    modulus: int = 8

    def __post_init__(self):
        if min(self.poll_m1, self.poll_cycles, self.wait_m1) < 0:
            raise ValueError('Negative loop cost')
        if self.wait_cycles <= 0 or self.modulus <= 0:
            raise ValueError('Positive wait period and refresh modulus required')

    @property
    def clock_period(self):
        return self.wait_cycles // gcd(self.wait_cycles, self.poll_cycles)

    @property
    def refresh_per_clock_period(self):
        n = self.clock_period
        return n*self.poll_m1 - self.wait_m1*(n*self.poll_cycles//self.wait_cycles)

    @property
    def state_period(self):
        """Exact first return of (clock residue, relative refresh residue)."""
        return self.clock_period*self.modulus // gcd(self.modulus, self.refresh_per_clock_period)

    def at(self, phase, polls):
        if not 0 <= phase < self.wait_cycles or polls < 0:
            raise ValueError('Invalid initial clock residue or poll count')
        waits, clock = divmod(phase + polls*self.poll_cycles, self.wait_cycles)
        return clock, (polls*self.poll_m1 - waits*self.wait_m1) % self.modulus

    def profile(self, phase):
        """All relative residues and first prefix covering all of them.

        Each prefix includes the initial event (zero extra polls). For a
        restricted orbit, all_refresh_events remains None: enumerating the
        entire clock period cannot fix the missing refresh residues.
        """
        seen = set()
        first_full = None
        for n in range(self.state_period):
            seen.add(self.at(phase, n)[1])
            if len(seen) == self.modulus:
                first_full = n + 1
                break
        return dict(residues=sorted(seen), all_refresh_events=first_full)

    def report(self):
        profiles = [self.profile(p) for p in range(self.wait_cycles)]
        full = [p['all_refresh_events'] for p in profiles]
        return dict(clock_period=self.clock_period, state_period=self.state_period,
                    residue_counts=sorted({len(p['residues']) for p in profiles}),
                    all_phases_cover_refresh=all(n is not None for n in full),
                    worst_cover_events=max(full) if all(n is not None for n in full) else None)
