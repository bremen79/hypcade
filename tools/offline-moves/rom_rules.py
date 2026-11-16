#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Small executable vocabulary for ROM rules and open decision DAGs.

An external CPU observation is not a random transition. Probability weights
must be supplied explicitly before an expectation can be calculated.
"""
from dataclasses import dataclass
from fractions import Fraction
from typing import Optional, Tuple


@dataclass(frozen=True)
class Origin:
    address: int
    meaning: str

    @property
    def pc(self):
        """Executable rule sites also use this address as the Z80 entry PC."""
        return self.address


@dataclass(frozen=True)
class Reward:
    commands: int = 0
    score: int = 0


@dataclass(frozen=True)
class ExternalRead:
    origin: Origin
    name: str
    mask: int


class ObservationRequired(ValueError):
    def __init__(self, request):
        self.request = request
        super().__init__('Bind %s at ROM %04X; no probability law is assumed' %
                         (request.name, request.origin.pc))


@dataclass(frozen=True)
class InputWindow:
    slot: int
    window: int
    control: Optional[int]
    outcome: int
    start_tick: int
    end_tick: int
    header: int
    extra: Optional[int]
    origin: Origin

    @property
    def label(self):
        return (self.control if self.control is not None else -1,
                self.slot * 3 + self.window, self.outcome)


@dataclass(frozen=True)
class Alternative:
    target: int
    observation: Optional[int] = None


@dataclass(frozen=True)
class Decision:
    source: int
    label: Tuple[int, int, int]
    kind: str
    reward: Reward
    alternatives: Tuple[Alternative, ...]
    origin: Origin
    external_read: Optional[ExternalRead] = None

    def expectation(self, values, distribution=None):
        if self.external_read is not None and distribution is None:
            raise ValueError('An external read has no default probability law')
        if distribution is None:
            if len(self.alternatives) != 1:
                raise ValueError('Bind the branch or supply an explicit distribution')
            return values[self.alternatives[0].target]
        return distribution.expectation([values[a.target] for a in self.alternatives])


@dataclass(frozen=True)
class Distribution:
    """Explicit caller assumption, never inferred from support or samples."""
    weights: Tuple[Fraction, ...]
    justification: str

    def __post_init__(self):
        if (not self.justification.strip() or not self.weights or
                any(not isinstance(p, Fraction) or p <= 0 for p in self.weights) or
                sum(self.weights) != 1):
            raise ValueError('Supply positive rational weights summing to one and a justification')

    def expectation(self, values):
        if len(values) != len(self.weights):
            raise ValueError('Distribution does not cover every outcome')
        return sum(p * value for p, value in zip(self.weights, values))


class Memory:
    """One physical byte store: queue/history aliases cannot diverge.

    ROM is immutable. Every write wraps to eight bits; addresses and words
    wrap to sixteen bits, as in the original Z80. Unmapped accesses fail.
    """
    BASE = 0xA000
    SIZE = 1024

    def __init__(self, rom, ram=None):
        self.rom = rom
        self.ram = bytearray(self.SIZE) if ram is None else bytearray(ram)
        if len(self.ram) != self.SIZE:
            raise ValueError('Expected the complete 1 KiB board RAM')
        self.reads, self.writes = set(), set()

    def read(self, address):
        address &= 65535
        self.reads.add(address)
        if self.BASE <= address < self.BASE + self.SIZE:
            return self.ram[address - self.BASE]
        if address < len(self.rom):
            return self.rom[address]
        raise ValueError('Unmapped ROM-rule read at %04X' % address)

    def write(self, address, value):
        address &= 65535
        if not self.BASE <= address < self.BASE + self.SIZE:
            raise ValueError('ROM rules cannot write ROM or unmapped memory: %04X' % address)
        self.writes.add(address)
        self.ram[address - self.BASE] = value & 255

    def word(self, address):
        return self.read(address) | self.read(address + 1) << 8

    def put_word(self, address, value):
        self.write(address, value)
        self.write(address + 1, value >> 8)

    def bits(self, address, *, set_bits=0, clear_bits=0):
        self.write(address, (self.read(address) | set_bits) & ~clear_bits)
