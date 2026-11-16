#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Executable SAE 1.0 gameplay rules, then a separate decision-DAG projection.

The concrete rules share a physical byte store and consume an observed R value
at its ROM read site. They do not predict instruction timing. The graph adapter
retains unresolved observations as alternatives, not independent randomness.
"""
from dataclasses import dataclass
from typing import Optional, Tuple

import rom_tables
from rom_rules import ExternalRead, InputWindow, Memory, ObservationRequired, Origin, Reward

SKILLS = ('cadet', 'captain', 'ace')
RULES = {
    'initial_queue': Origin(0x1D66, 'Copy the selected skill queue; initialize both player cursors'),
    'outcome': Origin(0x1C8C, 'High outcome changes scene; low outcome changes its step'),
    'queue_or_explicit': Origin(0x1D9F, 'Trailer bit 1 keeps an explicit episode; otherwise consume the queue'),
    'progress': Origin(0x1DE5, 'Count completed scenes; SAE NOPs the original harder-mode write'),
    'selector': Origin(0x1E24, 'Read physical variants and update shared history bytes'),
    'checkpoint': Origin(0x16B9, 'Update checkpoint only with operator-bank bit 7 enabled'),
    'restart': Origin(0x1465, 'Restart at the saved step or consume the next initial queue entry'),
    'death_animation': Origin(0x14F7, 'Death handler loads its noninteractive ending clip before restart'),
    'score_resume': Origin(0x095F, 'Flagged accepted input clears post-death award suppression'),
}
REFRESH = ExternalRead(Origin(0x1EB1, 'LD A,R followed by AND 1'), 'cpu.refresh', 1)


@dataclass(frozen=True)
class Record:
    scene: int
    step: int
    address: int
    end: int
    award: int
    flags: int
    default: int
    duration: int
    effects: int
    frame: int
    extension: Tuple[int, ...]
    windows: Tuple[InputWindow, ...]

    @property
    def death(self):
        return bool(self.flags & 16)

    @property
    def terminal(self):
        return bool(self.flags & 32)


@dataclass(frozen=True)
class Transition:
    ram: bytes
    reward: Reward
    reads: Tuple[Tuple[ExternalRead, int], ...]
    selected_episode: Optional[int]


class SaeRules:
    """Literal boundary-rule transcription for the active first player.

    Caller contract: a record has loaded and an outcome was accepted/timed out,
    or an accidental death has left another life available. Coins, physical
    input delivery, player switching and video waits remain emulator work.
    """
    def __init__(self, rom, skill='cadet', difficulty=0):
        if skill not in SKILLS or difficulty not in (0, 1):
            raise ValueError('Unsupported SAE skill/operator setting')
        self.rom, self.skill, self.difficulty = bytes(rom), skill, difficulty
        self.skill_number = SKILLS.index(skill)
        self._records = {}

    def memory(self, ram=None):
        return Memory(self.rom, ram)

    def record(self, scene, step):
        if not 0 <= scene < 77 or not 0 <= step < 128:
            raise ValueError('Not an SAE gameplay scene/step pointer')
        key = scene, step
        if key not in self._records:
            table = rom_tables.word(self.rom, 0x2571 + 2 * scene)
            address = rom_tables.word(self.rom, table + 2 * step)
            raw = rom_tables.decode_record(self.rom, address, 'sae')
            windows = []
            input_address = address
            for entry in raw['inputs']:
                tick = entry['delay_ticks']
                for window in entry['windows']:
                    control = entry['control']
                    if control is None and entry['rom_control'] in (5, 6, 9, 10):
                        control = entry['rom_control']
                    windows.append(InputWindow(entry['slot'], window['window'], control,
                        window['outcome'], tick, tick + window['ticks'], entry['header'], entry['extra'],
                        Origin(input_address, 'ROM input descriptor and unadjusted timer window')))
                    tick += window['ticks']
                input_address += (2 + len(entry['outcomes']) + int(entry['extra'] is not None)
                                  + 1 + len(entry['windows']))
            t = raw['trailer']
            self._records[key] = Record(scene, step, address, raw['end'], raw['award'], t[0], t[1],
                t[2] | t[3] << 8, t[4], t[5] | t[6] << 8, tuple(raw['extension']), tuple(windows))
        return self._records[key]

    def descriptor(self, episode):
        if not 1 <= episode <= 40:
            raise ValueError('Episode outside SAE gameplay descriptors')
        at = 0x2413 + 4 * episode
        return rom_tables.word(self.rom, at), self.rom[at + 2], self.rom[at + 3]

    def configured_memory(self):
        mem = self.memory()
        mem.write(0xA010, 102)
        bank = 152 ^ (128 if self.difficulty else 0)
        mem.write(0xA011, (bank & ~0x60) | (0x60, 0x20, 0x40)[self.skill_number])
        mem.write(0xA0D4, self.skill_number)
        return mem

    def initial_queue(self, mem):
        """ROM 1D66–1D9E. Preserve raw bytes, including the high bits."""
        ptr = mem.word(0x260B + 2 * mem.read(0xA0D4))
        mem.put_word(0xA05A, ptr)
        destination = 0xA080
        mem.put_word(0xA002, destination)
        while mem.read(ptr) != 255:
            mem.write(destination, mem.read(ptr))
            ptr += 1
            destination += 1
            mem.put_word(0xA002, destination)
            if destination > 0xA083:
                raise ValueError('SAE initial queue exceeds its audited three bytes')
        mem.put_word(0xA0D0, 0xA080)
        mem.put_word(0xA0D8, 0xA080)

    def apply_outcome(self, mem):
        """ROM 1C8C–1CAA. IY+2 is the loaded record's source scene."""
        outcome = mem.read(0xA012)
        if outcome & 128:
            mem.write(0xA00E, outcome)
            mem.write(0xA00F, 0)
            mem.bits(0xA008, clear_bits=1)
        else:
            mem.write(0xA00F, outcome)
            mem.write(0xA00E, mem.read(0xA202))

    def next_episode(self, mem, *, force_queue=False):
        """ROM 1D9F–1DC8; restart enters directly at 1DAB."""
        if not force_queue:
            if not mem.read(0xA012) & 128:
                return
            if mem.read(0xA205) & 2:
                self.apply_outcome(mem)
                return
        ptr = mem.word(0xA0D0)
        mem.write(0xA012, mem.read(ptr))
        mem.put_word(0xA0D0, ptr + 1)
        self.apply_outcome(mem)

    def select_episode(self, mem, refresh=None):
        """ROM 1E24–1F13, including SAE's patched revisit step ZERO."""
        if mem.read(0xA010) & 8:
            return ()
        if mem.read(0xA035) & 128:
            mem.bits(0xA035, clear_bits=128)
            return ()
        outcome = mem.read(0xA012)
        if not outcome & 128:
            return ()
        mem.write(0xA036, outcome)
        episode = outcome & 127
        mem.write(0xA054, episode)
        history_at = 0xA060 + episode
        mem.put_word(0xA055, history_at)
        mem.put_word(0xA0D2, history_at)
        mem.bits(0xA035, clear_bits=32)
        descriptor = 0x2413 + 4 * episode
        for offset in range(4):
            mem.write(0xA050 + offset, mem.read(descriptor + offset))
        history = mem.read(history_at)
        observations = ()
        if history:
            mem.bits(0xA035, set_bits=32)
            if history & 12:
                pick = 0 if history & 3 == 1 else 1
            else:
                pick = history & 1
        else:
            flags = mem.read(0xA052)
            if flags & 7 and not flags & 8:
                if refresh is None:
                    raise ObservationRequired(REFRESH)
                if not 0 <= refresh <= 255:
                    raise ValueError('Refresh observation must be an unsigned byte')
                pick = refresh & 1
                observations = ((REFRESH, refresh),)
            else:
                pick = 0
        mem.write(0xA057, pick)
        mem.write(0xA012, mem.read(mem.word(0xA050) + pick))
        self.apply_outcome(mem)
        if mem.read(0xA035) & 32:
            mem.write(0xA00F, 0)
        mem.bits(history_at, set_bits=1 << pick)
        return observations

    def progress(self, mem):
        """ROM 1DE5–1E0C; the last two bytes are NOPs in SAE."""
        if not mem.read(0xA012) & 128 or mem.read(0xA035) & 16:
            return
        mem.write(0xA0D5, mem.read(0xA0D5) + 1)
        threshold = 6 if mem.read(0xA011) & 16 else 4
        if mem.read(0xA0D5) != threshold:
            return
        # No harder-mode flag write: preserve the SAE patch.

    def checkpoint(self, mem, record):
        """ROM 16B9–16D3; operator bank, NOT skill, gates SAE checkpoints."""
        if mem.read(0xA011) & 128 and record.effects & 1:
            mem.write(0xA037, record.extension[-1])

    def install_record(self, mem, record):
        # Loader 166E–16B8: normalized footer layout. Input timer loading and
        # score publication are not simulated by these boundary rules.
        for offset, value in ((0, record.flags), (1, record.default), (2, record.scene | 128),
                              (3, record.frame & 255), (4, record.frame >> 8), (5, record.effects),
                              (14, record.duration & 255), (15, record.duration >> 8)):
            mem.write(0xA200 + offset, value)
        extension = iter(record.extension)
        for flag, offset in ((32, 7), (64, 9)):
            if record.effects & flag:
                mem.write(0xA200 + offset, next(extension))
                mem.write(0xA201 + offset, next(extension))

    def new_game(self):
        mem = self.configured_memory()
        self.initial_queue(mem)
        mem.write(0xA037, 1)
        mem.write(0xA012, 129)
        self.select_episode(mem)
        record = self.record(mem.read(0xA00E) & 127, mem.read(0xA00F))
        self.install_record(mem, record)
        self.checkpoint(mem, record)
        return bytes(mem.ram)

    def timed(self, rom_path, *, build_dir=None, start_delay=0):
        """Compute accepted outcomes/R from physical input times, then bind rules."""
        from sae_timing import SaeTimedRules
        return SaeTimedRules(self, rom_path, build_dir=build_dir, start_delay=start_delay)

    def death_animation(self, ram, outcome):
        """Routing part of 14F7–152F; life counting/clip timing stay in the CPU.

        Death records are absorbing in surviving-policy graphs. Actual timed
        execution must still play their automatic clip before calling 1465.
        """
        mem = self.memory(ram)
        record = self.record(mem.read(0xA00E) & 127, mem.read(0xA00F))
        if not record.death:
            raise ValueError('Death animation requires a death record')
        self.install_record(mem, record)
        mem.write(0xA012, outcome)
        self.apply_outcome(mem)
        mem.bits(0xA00A, set_bits=2)
        mem.bits(0xA035, set_bits=128)
        mem.write(0xA0D5, 0)
        target = self.record(mem.read(0xA00E) & 127, mem.read(0xA00F))
        self.install_record(mem, target)
        self.checkpoint(mem, target)
        return Transition(bytes(mem.ram), Reward(), (), None)

    def transition(self, ram, outcome, *, control=0, header=None, refresh=None, recovery=False):
        """Execute one accepted/automatic outcome, or one surviving life restart.

        Reward convention for the DAG: include the source record's award once.
        This is path accounting, not the hardware score-publication instant.
        """
        mem = self.memory(ram)
        record = self.record(mem.read(0xA00E) & 127, mem.read(0xA00F))
        award = 0 if mem.read(0xA00A) & 2 else record.award
        if record.flags & 64:
            raise ValueError('System record outside the gameplay boundary contract')
        if record.effects & (4 | 8 | 32 | 64):
            raise ValueError('Untranscribed completion/replay effect at ROM %04X' % record.address)
        self.install_record(mem, record)
        if recovery:
            animation_end = (record.terminal and (record.scene, record.step) != (25, 63)
                             and mem.read(0xA035) & 128)
            if not record.death and not animation_end:
                raise ValueError('Life restart requires an actual death record')
            # Caller has already handled the death/life-count routine. 1465:
            mem.bits(0xA00A, set_bits=2)
            mem.bits(0xA035, set_bits=128)
            mem.write(0xA012, record.scene | 128)
            mem.write(0xA00F, 0)
            checkpoint = mem.read(0xA037)
            if checkpoint & 128:
                self.next_episode(mem, force_queue=True)
                mem.bits(0xA035, clear_bits=128)
                mem.write(0xA037, 1)
            else:
                mem.write(0xA00F, checkpoint)
        else:
            if record.death or record.terminal:
                raise ValueError('No accepted gameplay action from a terminal record')
            if outcome == 255:
                raise ValueError('Ignored input is not an accepted transition')
            if control:
                candidates = {w.header for w in record.windows
                              if w.label[0] == control and w.outcome == outcome}
                if header is None:
                    if len(candidates) != 1:
                        raise ValueError('Accepted input must identify its ROM descriptor header')
                    header = next(iter(candidates))
                if header not in candidates:
                    raise ValueError('Accepted input header absent from source ROM record')
                if header & 16:
                    mem.bits(0xA00A, clear_bits=2)
            mem.write(0xA012, outcome)
            self.apply_outcome(mem)
            if outcome & 128:
                mem.write(0xA037, 1)
                if mem.read(0xA0D4):
                    self.progress(mem)
                self.next_episode(mem)
                mem.bits(0xA035, clear_bits=8)
            # Otherwise 1F14/1F57 have no effect under the guarded trailer bits.
        reads = self.select_episode(mem, refresh)
        selected = mem.read(0xA036) & 127 if 0xA036 in mem.writes else None
        target = self.record(mem.read(0xA00E) & 127, mem.read(0xA00F))
        self.install_record(mem, target)
        self.checkpoint(mem, target)
        return Transition(bytes(mem.ram), Reward(0 if recovery else int(bool(control)),
                          0 if recovery else award), reads, selected)


@dataclass(frozen=True)
class Point:
    episode: int
    scene: int
    step: int
    cursor: int
    checkpoint: int
    queue: Tuple[int, ...]
    score_suppressed: bool = False


class SaeGraph:
    """Open, timing-relaxed DAG generated by the executable rules above.

    Non-aliased history is erased only after the verifier proves no first
    revisit can occur. Queue/history aliases remain physical bytes. This is NOT a claim
    that an observed refresh bit is independent of accepted-input timing.
    """
    def __init__(self, rules):
        self.rules = rules
        self.recoveries = []
        self._initial = rules.new_game()
        self.queue_length = rules.memory(self._initial).word(0xA002) - 0xA080
        self.external_sites = set()

    def project(self, ram):
        mem = self.rules.memory(ram)
        return Point(mem.read(0xA036) & 127, mem.read(0xA00E) & 127, mem.read(0xA00F),
                     mem.word(0xA0D0) - 0xA080, mem.read(0xA037),
                     tuple(mem.read(0xA080 + i) for i in range(self.queue_length)),
                     bool(mem.read(0xA00A) & 2))

    def materialize(self, point):
        mem = self.rules.configured_memory()
        for i, value in enumerate(point.queue):
            mem.write(0xA080 + i, value)
        mem.write(0xA036, point.episode | 128)
        mem.write(0xA00E, point.scene | 128)
        mem.write(0xA00F, point.step)
        mem.write(0xA037, point.checkpoint)
        mem.write(0xA00A, 2 if point.score_suppressed else 0)
        mem.put_word(0xA0D0, 0xA080 + point.cursor)
        # No separate history map: never overwrite an aliased queue byte.
        if not 0xA080 <= 0xA060 + point.episode < 0xA080 + self.queue_length:
            mem.write(0xA060 + point.episode, 1)
        return bytes(mem.ram)

    def start(self):
        return self.project(self._initial)

    def record_for(self, point):
        record = self.rules.record(point.scene, point.step)
        return dict(award=0 if point.score_suppressed else record.award, death=record.death)

    def won(self, point):
        record = self.rules.record(point.scene, point.step)
        if record.terminal and not record.death and (point.scene, point.step) != (25, 63):
            raise ValueError('Unclassified surviving terminal at ROM %04X' % record.address)
        return (point.scene, point.step) == (25, 63)

    def resolve(self, point, outcome, control=0, *, header=None, recovery=False):
        if outcome == 255 and not recovery:
            return []
        ram = self.materialize(point)
        try:
            result = self.rules.transition(ram, outcome, control=control, header=header, recovery=recovery)
            return [result]
        except ObservationRequired as pending:
            self.external_sites.add(pending.request.origin.pc)
            # Enumerate SUPPORT, not a distribution. Binding is at LD A,R.
            return [self.rules.transition(ram, outcome, control=control,
                                          header=header, refresh=value, recovery=recovery)
                    for value in range(pending.request.mask + 1)]

    def successors(self, point, outcome, control=0, *, header=None, recovery=False):
        return sorted({self.project(result.ram) for result in
                       self.resolve(point, outcome, control, header=header, recovery=recovery)}, key=repr)

    def actions(self, point):
        record = self.rules.record(point.scene, point.step)
        if record.death or record.terminal:
            return []
        labels = [((0, 0, record.default), None)] + [(w.label, w.header) for w in record.windows]
        return [(label, self.successors(point, label[2], label[0], header=header)) for label, header in labels]

    def coverage_seeds(self, limit=12000):
        nodes = [self.start()]
        seen = set(nodes)
        self.recoveries = []
        for point in nodes:
            if len(nodes) > limit:
                raise ValueError('SAE projection exceeded its low-memory state budget')
            if self.rules.record(point.scene, point.step).death:
                targets = self.successors(point, 0, recovery=True)
                self.recoveries.append((point, targets))
            else:
                targets = [t for label, ts in self.actions(point) for t in ts]
            for target in targets:
                if target not in seen:
                    seen.add(target)
                    nodes.append(target)
        return nodes
