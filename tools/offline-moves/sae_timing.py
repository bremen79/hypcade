#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exact CPU/IRQ/player timing primitive for SAE's executable rules.

Two native machine slots, not a CPU-state graph. Timed physical inputs compute
acceptance and R reads. The caller cannot choose a refresh value.
"""
import ctypes as c
from dataclasses import dataclass
import hashlib
import math
import os
from pathlib import Path
import subprocess

import moves
import score_routes

ROOT = Path(__file__).resolve().parent
RAM = c.c_uint8 * 1024


@dataclass(frozen=True)
class TimedAction:
    control: int
    press_cycle: int
    release_cycle: int
    until_cycle: int

    def __post_init__(self):
        if (type(self.control) is not int or not 0 <= self.control <= 16 or
                any(type(t) is not int or not 0 <= t < 2**64 for t in
                    (self.press_cycle, self.release_cycle, self.until_cycle)) or
                not self.press_cycle <= self.release_cycle <= self.until_cycle):
            raise ValueError('Invalid timed input: use control 0..16 and ordered integer CPU cycles')


@dataclass(frozen=True)
class TimingEvent:
    cycle: int
    kind: str
    scene: int
    step: int
    episode: int
    outcome: int
    control: int
    refresh: int
    score: int
    lives: int
    runtime_slot: int
    runtime_window: int
    ram: bytes


@dataclass(frozen=True)
class TimingState:
    cycle: int
    pc: int
    refresh: int
    next_irq: int
    frame: int
    player_state: int
    score: int
    lives: int
    episode: int
    scene: int
    step: int
    checkpoint: int
    ram: bytes
    decision_hash: str
    victory_hash: str


def identity():
    result = score_routes.source_identity()
    for name in ('sae_timing.c', 'sae_timing.py', 'sae_rules.py', 'rom_rules.py'):
        result[str((ROOT / name).relative_to(ROOT.parents[1]))] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    return result


def build(folder):
    moves.verify_vendor()
    folder = Path(folder).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    sources = identity()
    tag = hashlib.sha256(str(sorted(sources.items())).encode()).hexdigest()[:16]
    library = folder / ('sae-timing-' + tag + '.so')
    if not library.is_file():
        src = ROOT / 'vendor/src'
        subprocess.run([os.environ.get('CC', 'cc'), '-O2', '-std=c11', '-fPIC', '-shared',
                        '-ffp-contract=off', '-D_POSIX_C_SOURCE=200809L', '-Wall', '-Wextra', '-Werror',
                        '-I' + str(src), str(ROOT / 'sae_timing.c'),
                        *[str(src / name) for name in moves.SOURCES], '-lz', '-lm', '-o', str(library)], check=True)
        if identity() != sources:
            raise ValueError('Sources changed while building the timing primitive')
    return library


class SaeTiming:
    @staticmethod
    def build_library(folder):
        return build(folder)

    def __init__(self, rom, *, skill='cadet', difficulty=0, start_delay=0, build_dir=None):
        if skill not in ('cadet', 'captain', 'ace') or difficulty not in (0, 1):
            raise ValueError('Unsupported SAE configuration')
        if not math.isfinite(start_delay) or not 0 <= start_delay <= 3600:
            raise ValueError('Invalid start delay')
        self._rom_path, self._skill_bytes = os.fsencode(Path(rom).resolve()), skill.encode()
        moves.identity(Path(rom), 'sae')
        self.skill, self.difficulty = skill, difficulty
        library = self.build_library(build_dir or ROOT.parents[1] / 'local-tools/sae-timing-build')
        self.native = c.CDLL(str(library))
        n = self.native
        n.sae_timing_open.argtypes = [c.c_char_p, c.c_char_p, c.c_uint, c.c_double]
        n.sae_timing_open.restype = c.c_void_p
        n.sae_timing_close.argtypes = [c.c_void_p]
        n.sae_timing_action.argtypes = [c.c_void_p, c.c_uint, c.c_uint64, c.c_uint64, c.c_uint64]
        for name in ('sae_timing_wait', 'sae_timing_finish'):
            getattr(n, name).argtypes = [c.c_void_p, c.c_uint64]
        for name in ('sae_timing_save', 'sae_timing_restore', 'sae_timing_event_count'):
            getattr(n, name).argtypes = [c.c_void_p]
        n.sae_timing_event_count.restype = c.c_uint
        n.sae_timing_event.argtypes = [c.c_void_p, c.c_uint, c.POINTER(c.c_uint64), c.POINTER(c.c_uint8)]
        n.sae_timing_state.argtypes = [c.c_void_p, c.POINTER(c.c_uint64), c.POINTER(c.c_uint8), c.c_char_p]
        n.sae_timing_action_times.argtypes = [c.c_void_p, c.POINTER(c.c_uint64)]
        n.sae_timing_memory_bytes.argtypes = []
        n.sae_timing_memory_bytes.restype = c.c_uint64
        self._handle = n.sae_timing_open(self._rom_path, self._skill_bytes, difficulty, start_delay)
        self._saved = False
        if not self._handle:
            raise ValueError('Original ROM failed to reach the first input decision')

    def close(self):
        if self._handle:
            self.native.sae_timing_close(self._handle)
            self._handle = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def _live(self):
        if not self._handle:
            raise ValueError('Timing session is closed')
        return self._handle

    def state(self):
        fields, ram, hashes = (c.c_uint64 * 12)(), RAM(), c.create_string_buffer(66)
        if not self.native.sae_timing_state(self._live(), fields, ram, hashes):
            raise ValueError('Cannot read timing state')
        values = list(fields)
        for i in (4, 6, 7):
            if values[i] >= 2**63:
                values[i] -= 2**64
        return TimingState(*values, bytes(ram), hashes.raw[:32].decode(), hashes.raw[33:65].decode())

    def _events(self, result):
        if not result:
            raise ValueError('Timing primitive rejected the operation or exceeded its bounded event log')
        events = []
        names = ('', 'ready', 'outcome', 'refresh', 'restart', 'success', 'accepted')
        for i in range(self.native.sae_timing_event_count(self._live())):
            fields, ram = (c.c_uint64 * 12)(), RAM()
            if not self.native.sae_timing_event(self._handle, i, fields, ram):
                raise ValueError('Incomplete timing event')
            values = list(fields[2:])
            for j in (6, 7, 8, 9):
                if values[j] >= 2**63:
                    values[j] -= 2**64
            events.append(TimingEvent(fields[0], names[fields[1]], *values, bytes(ram)))
        return events

    def action(self, action):
        if action.press_cycle < self.state().cycle:
            raise ValueError('Cannot schedule an input in the past')
        return self._events(self.native.sae_timing_action(self._live(), action.control,
                            action.press_cycle, action.release_cycle, action.until_cycle))

    def wait(self, until_cycle):
        if type(until_cycle) is not int or until_cycle < self.state().cycle or until_cycle >= 2**64:
            raise ValueError('Invalid wait endpoint')
        return self._events(self.native.sae_timing_wait(self._live(), until_cycle))

    def finish(self, maximum_extra_cycles=60 * 4000000):
        if type(maximum_extra_cycles) is not int or not 0 <= maximum_extra_cycles < 2**64:
            raise ValueError('Invalid completion budget')
        return self._events(self.native.sae_timing_finish(self._live(), maximum_extra_cycles))

    def save(self):
        if not self.native.sae_timing_save(self._live()):
            raise ValueError('Cannot checkpoint timing state')
        self._saved = True

    def restore(self):
        if not self._saved or not self.native.sae_timing_restore(self._live()):
            raise ValueError('No timing checkpoint available')

    def action_times(self):
        times = (c.c_uint64 * 2)()
        if not self.native.sae_timing_action_times(self._live(), times):
            raise ValueError('Missing executed action times')
        return tuple(times)

    @property
    def memory_bytes(self):
        return self.native.sae_timing_memory_bytes()


@dataclass(frozen=True)
class TimedBoundary:
    cycle: int
    ready_cycle: int
    source: object
    target: object
    control: int
    outcome: int
    recovery: bool
    refresh: object
    rule_reward: object
    kind: str
    accepted_cycle: object
    runtime_slot: int
    runtime_window: int


@dataclass(frozen=True)
class TimedResult:
    state: TimingState
    reward: object
    boundaries: tuple
    events: tuple
    executed_action: object = None


@dataclass(frozen=True)
class _Pending:
    cycle: int
    ram: bytes
    control: int
    outcome: int
    recovery: bool
    refresh: object = None
    death_animation: bool = False
    accepted: object = None


class SaeTimedRules:
    """Bind time-dependent ROM effects to the readable SAE rules.

    The small native timing primitive computes which outcome is accepted and
    every R read from actual timed inputs. Python transcribes and checks every
    resulting boundary. This is hybrid execution, not a second CPU emulator or
    a claim that the untimed DAG has acquired a timing-optimal policy.
    """
    def __init__(self, rules, rom, *, build_dir=None, start_delay=0, timing_factory=SaeTiming):
        from sae_rules import SaeGraph
        import rom_tables
        if rom_tables.load(rom, 'sae') != rules.rom:
            raise ValueError('Timing primitive and rule transcription must use the same ROM')
        self.rules = rules
        self.projection = SaeGraph(rules)
        self.timing = timing_factory(rom, skill=rules.skill, difficulty=rules.difficulty,
                                start_delay=start_delay, build_dir=build_dir)
        self._pending = None
        self._selected = None
        self._point = self.projection.project(self.timing.state().ram)
        self._accepted = 0
        self._success = None
        self._saved_binding = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.timing.close()

    def state(self):
        return self.timing.state()

    def _consume(self, before, events):
        from dataclasses import replace
        from rom_rules import Reward
        transitions = []
        accepted_before = self._accepted
        for event in events:
            if event.kind == 'accepted':
                if self._selected is not None or self._pending is not None:
                    raise ValueError('Overlapping accepted inputs in the ROM boundary')
                record = self.rules.record(event.scene, event.step)
                candidates = [w for w in record.windows
                              if (w.header & 15 or 16) == event.control and w.outcome == event.outcome
                              and w.end_tick > w.start_tick]
                if not candidates:
                    raise ValueError('Timed CPU accepted an input/outcome absent from the decoded ROM windows')
                self._selected = event
                self._accepted += 1
            elif event.kind == 'outcome':
                record = self.rules.record(event.scene, event.step)
                if record.terminal:
                    continue
                if self._pending is not None:
                    raise ValueError('A second ROM outcome arrived before the previous record loaded')
                if event.control:
                    if self._selected is None or ((self._selected.scene,self._selected.step,
                        self._selected.control,self._selected.outcome) !=
                        (event.scene,event.step,event.control,event.outcome)):
                        raise ValueError('Applied outcome differs from the ROM-selected input')
                elif self._selected is not None:
                    raise ValueError('Default outcome replaced an accepted input')
                self._pending = _Pending(event.cycle, event.ram, event.control, event.outcome,
                                         False, death_animation=record.death, accepted=self._selected)
                self._selected = None
            elif event.kind == 'restart':
                if self._pending is not None:
                    raise ValueError('Unexpected life restart during an unfinished boundary')
                self._pending = _Pending(event.cycle, event.ram, 0, 0, True)
            elif event.kind == 'refresh':
                if self._pending is None or self._pending.refresh is not None:
                    raise ValueError('Unmatched/multiple refresh read outside the transcribed boundary')
                self._pending = replace(self._pending, refresh=event.refresh)
            elif event.kind == 'ready':
                actual = self.projection.project(event.ram)
                if self._pending is None:
                    if actual != self._point:
                        raise ValueError('Unmodeled record load without outcome or life restart')
                    continue
                pending = self._pending
                if pending.death_animation:
                    predicted = self.rules.death_animation(pending.ram, pending.outcome)
                else:
                    ram = bytearray(pending.ram)
                    ram[10] = (ram[10] & ~2) | (2 if self._point.score_suppressed else 0)
                    header = (pending.accepted.ram[0xE0 + 16 * pending.accepted.runtime_slot]
                              if pending.accepted else None)
                    predicted = self.rules.transition(ram, pending.outcome, control=pending.control,
                                                       header=header, refresh=pending.refresh, recovery=pending.recovery)
                target = self.projection.project(predicted.ram)
                if target != actual:
                    raise ValueError('Timed ROM/rule mismatch: predicted %r; actual %r' % (target, actual))
                if bool(predicted.reads) != (pending.refresh is not None):
                    raise ValueError('ROM and transcription disagree about the timing-dependent read')
                record = self.rules.record(event.scene, event.step)
                actual_frame = int.from_bytes(event.ram[0x203:0x205], 'little')
                if actual_frame != record.frame:
                    raise ValueError('Actual timed loader frame differs from the ROM record')
                transitions.append(TimedBoundary(pending.cycle, event.cycle,
                    self._point, target, pending.control,
                    pending.outcome, pending.recovery, pending.refresh, predicted.reward,
                    'restart' if pending.recovery else 'death-animation' if pending.death_animation else 'ordinary',
                    pending.accepted.cycle if pending.accepted else None,
                    pending.accepted.runtime_slot if pending.accepted else -1,
                    pending.accepted.runtime_window if pending.accepted else -1))
                self._point, self._pending = actual, None
            elif event.kind == 'success':
                if (event.scene, event.step) != (25, 63) or self._pending is not None:
                    raise ValueError('Unclassified timed terminal')
                self._success = event
        state = self.timing.state()
        return TimedResult(state, Reward(self._accepted - accepted_before, state.score - before.score),
                           tuple(transitions), tuple(events))

    def step(self, action):
        from dataclasses import replace
        before = self.state()
        result = self._consume(before, self.timing.action(action))
        press, release = self.timing.action_times()
        return replace(result, executed_action=TimedAction(action.control, press, release, result.state.cycle))

    def wait(self, until_cycle):
        before = self.state()
        return self._consume(before, self.timing.wait(until_cycle))

    def finish(self, maximum_extra_cycles=60 * 4000000):
        before = self.state()
        result = self._consume(before, self.timing.finish(maximum_extra_cycles))
        if self._success is None:
            raise ValueError('Timing primitive did not execute the successful ROM end handler')
        return result

    def save(self):
        self.timing.save()
        self._saved_binding = self._pending, self._selected, self._point, self._accepted, self._success

    def restore(self):
        if self._saved_binding is None:
            raise ValueError('No checkpoint for the timed rule bindings')
        self.timing.restore()
        self._pending, self._selected, self._point, self._accepted, self._success = self._saved_binding
