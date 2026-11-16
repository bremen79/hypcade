#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Space Ace A3 ROM boundary rules and finite reward/progress audits.

A3 differs from SAE: 1BD7 adds a fixed award without A00A.1 suppression;
1E0A sets harder mode. Harder mode is separate from selected player skill.
Queue/replay/checkpoint transitions are transcribed in cine_recovery_model;
verify_cine_recovery.audit checks those transitions with the original Z80.
"""
import cine_recovery_model
import rom_tables
from rom_rules import Origin

RULES = {
    'award_load': Origin(0x1707, 'Double the indexed fixed score into A013/A014'),
    'award_transfer': Origin(0x1BD7, 'Add the pending award to score; no post-death suppression gate'),
    'progress': Origin(0x1DE5, 'Increment A0D5 and monotonically set A035.4 at count 4 or 6'),
    'replay': Origin(0x1F57, 'Skill-specific bounded physical replay with saved checkpoint'),
    'restart': Origin(0x1465, 'Resume checkpoint, preserving replay state, or consume queue'),
}


class Model(cine_recovery_model.Model):
    def __init__(self, rom, skill):
        super().__init__(rom, 'ace', skill)

    def graph(self):
        import rom_proof
        return rom_proof.closure(self, self.coverage_seeds())


def audit_rewards_and_progress(rom, kernel):
    """Exhaust score indices/gate bits and all byte progress counters."""
    cases = 0
    if rom[0x1E0A:0x1E0C] != bytes.fromhex('cbe6'):
        raise ValueError('A3 harder-mode write changed')
    for rank in range(16):
        award = 2 * rom_tables.word(rom, 0x2115 + 2 * rank)
        ram = bytearray(1024)
        ram[0x200] = rank
        actual, _ = kernel.call(ram, 0x1707, stop=0x171E)
        if int.from_bytes(actual[0x13:0x15], 'little') != award:
            raise ValueError('A3 fixed score load differs from ROM')
        cases += 1
        for gate in (0, 2):
            ram = bytearray(1024)
            ram[0xA] = gate
            ram[0x13:0x15] = award.to_bytes(2, 'little')
            baseline = 0x12FFFE
            ram[0x32:0x35] = baseline.to_bytes(3, 'little')
            # 1BEF publishes score to hardware; stop before that side effect.
            actual, _ = kernel.call(ram, 0x1BD7, stop=0x1BEF if award & 255 else 0xDEAD)
            expected = baseline + award if award & 255 else baseline
            if int.from_bytes(actual[0x32:0x35], 'little') != expected:
                raise ValueError('A3 award transfer differs from ROM')
            cases += 1
    for threshold in (4, 6):
        for count in range(256):
            for hard in (0, 16):
                for outcome in (1, 128):
                    ram = bytearray(1024)
                    ram[0x10] = 4 if threshold == 6 else 0
                    ram[0x12], ram[0x35], ram[0xD5] = outcome, hard, count
                    actual, _ = kernel.call(ram, 0x1DE5)
                    after = (count + 1) & 255 if outcome & 128 and not hard else count
                    flag = hard | (16 if outcome & 128 and after == threshold else 0)
                    if actual[0xD5] != after or actual[0x35] != flag:
                        raise ValueError('A3 progression differs from ROM')
                    if actual[0xD4] != ram[0xD4]:
                        raise ValueError('Harder mode unexpectedly changes player skill')
                    cases += 1
    return dict(original_rom_cases=cases, score='Fixed per-record doubled award; no SAE score suppression',
        progress='Monotone harder-mode flag at 4/6 completions; selected skill remains unchanged',
        timing_limit='Input acceptance and harder-mode window changes need separate loader/delivery validation')
