#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Original synthetic fixtures; no commercial ROM or native build required."""
from fractions import Fraction
import unittest

from rom_rules import Alternative, Decision, Distribution, ExternalRead, Memory, ObservationRequired, Origin, Reward
from sae_rules import REFRESH, SaeRules, SaeGraph


def fixture():
    rom = bytearray(40960)
    for skill, queue in enumerate(((130, 131, 132), (130, 143, 144), (154, 155, 156))):
        ptr = 0x2700 + skill * 16
        rom[0x260B + skill * 2:0x260D + skill * 2] = ptr.to_bytes(2, 'little')
        rom[ptr:ptr + 4] = bytes((*queue, 255))
    for ep in range(1, 41):
        ptr = 0x2800 + ep * 2
        rom[0x2413 + ep * 4:0x2417 + ep * 4] = bytes((ptr & 255, ptr >> 8, int(ep != 1), 0))
        rom[ptr:ptr + 2] = bytes((129 if ep == 1 else 128 + 2 * ep - 5, 128 + 2 * ep - 4))
    rom[0x2573:0x2575] = (0x3000).to_bytes(2, 'little')
    rom[0x3000:0x3002] = (0x4000).to_bytes(2, 'little')
    rom[0x4000:0x4008] = bytes((0, 130, 10, 0, 1, 0, 0, 5))
    rom[0x258B:0x258D] = (0x3100).to_bytes(2, 'little')
    rom[0x3124:0x3126] = (0x4100).to_bytes(2, 'little')
    rom[0x2505:0x2507] = (123).to_bytes(2, 'little')
    rom[0x4100:0x410E] = bytes((0x90, 1, 20, 128, 10, 5, 1, 23, 20, 0, 1, 0, 0, 19))
    return bytes(rom)


class MemoryTest(unittest.TestCase):
    def test_aliases_wrapping_and_immutable_rom(self):
        mem = Memory(bytes(65536))
        history_at, queue_at = 0xA060 + 34, 0xA080 + 2
        mem.write(queue_at, 156)
        mem.bits(history_at, set_bits=2)
        self.assertEqual(mem.read(queue_at), 158)
        mem.write(queue_at, 511)
        self.assertEqual(mem.read(history_at), 255)
        mem.put_word(0xA100, 0x1FFFF)
        self.assertEqual(mem.word(0xA100), 65535)
        self.assertEqual(mem.word(0xFFFF), 0)
        with self.assertRaisesRegex(ValueError, 'cannot write ROM'):
            mem.write(0, 1)


class RuleTest(unittest.TestCase):
    def retry_fixture(self, header=0x90):
        rom = bytearray(fixture())
        if header == 0x80:
            rom[0x4100:0x410D] = bytes((0x80, 1, 20, 10, 5, 1, 23, 20, 0, 1, 0, 0, 19))
        else:
            rom[0x4100] = header
        for step, at, flags, default in ((19, 0x4200, 1, 20), (20, 0x4300, 1, 21),
                                         (29, 0x4400, 16, 30), (30, 0x4500, 32, 0)):
            rom[0x3100 + 2*step:0x3102 + 2*step] = at.to_bytes(2, 'little')
            rom[at:at+8] = bytes((flags, default, 10, 0, 0, 0, 0, 0))
        rules = SaeRules(rom)
        mem = rules.configured_memory()
        rules.initial_queue(mem)
        mem.write(0xA036, 136)
        mem.write(0xA00E, 141)
        mem.write(0xA00F, 18)
        mem.write(0xA037, 19)
        mem.write(0xA00A, 2)
        return rules, mem

    def test_flagged_retry_input_restores_future_awards_only(self):
        rules, mem = self.retry_fixture()
        result = rules.transition(mem.ram, 20, control=16)
        self.assertEqual(result.reward.score, 0)  # already suppressed at load
        self.assertEqual(result.ram[10] & 2, 0)
        graph = SaeGraph(rules)
        point = graph.project(result.ram)
        self.assertFalse(point.score_suppressed)
        self.assertEqual(graph.record_for(point)['award'], 246)
        self.assertEqual(graph.project(graph.materialize(point)), point)

    def test_unflagged_retry_input_keeps_awards_suppressed(self):
        rules, mem = self.retry_fixture(0x80)
        result = rules.transition(mem.ram, 20, control=16)
        self.assertEqual(result.ram[10] & 2, 2)
        graph = SaeGraph(rules)
        self.assertEqual(graph.record_for(graph.project(result.ram))['award'], 0)

    def test_diagonal_is_a_real_rom_control(self):
        rules, mem = self.retry_fixture(0x95)
        self.assertEqual(rules.record(13, 18).windows[0].label, (5, 0, 20))
        result = rules.transition(mem.ram, 20, control=5)
        self.assertEqual(result.reward.commands, 1)
        self.assertEqual(result.ram[10] & 2, 0)

    def test_death_animation_and_restart_keep_score_suppression(self):
        rules, mem = self.retry_fixture()
        mem.write(0xA00F, 29)
        mem.write(0xA00A, 0)
        animation = rules.death_animation(mem.ram, 30)
        self.assertEqual(animation.ram[10] & 2, 2)
        restarted = rules.transition(animation.ram, 0, recovery=True)
        self.assertEqual(restarted.ram[15], 19)
        self.assertEqual(restarted.ram[10] & 2, 2)

    def test_record_preserves_raw_window_guard_and_reward(self):
        rules = SaeRules(fixture())
        rec = rules.record(13, 18)
        self.assertEqual(rec.award, 246)
        self.assertEqual(rec.extension, (19,))
        window, = rec.windows
        self.assertEqual(window.label, (16, 0, 20))
        self.assertEqual((window.start_tick, window.end_tick), (10, 15))
        self.assertEqual((window.header, window.extra), (0x90, 128))

    def test_ignored_input_and_untranscribed_effect_fail_closed(self):
        rom = fixture()
        rules = SaeRules(rom)
        mem = rules.configured_memory()
        mem.write(0xA00E, 141)
        mem.write(0xA00F, 18)
        before = bytes(mem.ram)
        with self.assertRaisesRegex(ValueError, 'Ignored input'):
            rules.transition(before, 255)
        self.assertEqual(bytes(mem.ram), before)
        changed = bytearray(rom)
        changed[0x410A] = 64
        rules = SaeRules(changed)
        with self.assertRaisesRegex(ValueError, 'Untranscribed'):
            rules.transition(before, 20)

    def test_game_initialization_and_operator_checkpoint_gate(self):
        for skill in ('cadet', 'captain', 'ace'):
            for difficulty in (0, 1):
                rules = SaeRules(fixture(), skill, difficulty)
                mem = rules.memory(rules.new_game())
                self.assertEqual(mem.read(0xA00E), 129)
                self.assertEqual(mem.word(0xA0D0), 0xA080)
                self.assertEqual(mem.read(0xA061), 1)
                self.assertEqual(mem.read(0xA037), 1 if difficulty else 5)

    def test_refresh_is_an_observation_not_implicit_randomness(self):
        rules = SaeRules(fixture())
        mem = rules.configured_memory()
        rules.initial_queue(mem)
        mem.write(0xA012, 168)
        with self.assertRaises(ObservationRequired) as caught:
            rules.select_episode(mem)
        self.assertEqual(caught.exception.request, REFRESH)
        outputs = []
        for refresh in (0, 1, 254, 255):
            m = rules.configured_memory()
            m.write(0xA012, 168)
            observations = rules.select_episode(m, refresh)
            outputs.append(m.read(0xA00E))
            self.assertEqual(observations, ((REFRESH, refresh),))
        self.assertEqual(outputs[0], outputs[2])
        self.assertEqual(outputs[1], outputs[3])
        self.assertNotEqual(outputs[0], outputs[1])

    def test_existing_history_can_override_refresh(self):
        rules = SaeRules(fixture())
        for history, pick in ((1, 1), (2, 0), (3, 1), (5, 0), (6, 1)):
            mem = rules.configured_memory()
            mem.write(0xA012, 138)
            mem.write(0xA06A, history)
            self.assertEqual(rules.select_episode(mem), ())
            self.assertEqual(mem.read(0xA057), pick)
            self.assertEqual(mem.read(0xA06A), history | (1 << pick))
            self.assertEqual(mem.read(0xA00F), 0)

    def test_episode_34_mutates_the_actual_unread_queue_byte(self):
        rules = SaeRules(fixture(), 'ace')
        mem = rules.configured_memory()
        rules.initial_queue(mem)
        mem.write(0xA012, 128 | 34)
        rules.select_episode(mem)
        self.assertEqual(mem.read(0xA082), 158)
        mem.put_word(0xA0D0, 0xA082)
        mem.write(0xA205, 0)
        mem.write(0xA012, 128)
        rules.next_episode(mem)
        self.assertEqual(mem.read(0xA012), 158)
        self.assertEqual(mem.word(0xA0D0), 0xA083)

    def test_explicit_episode_does_not_consume_the_queue(self):
        rules = SaeRules(fixture())
        mem = rules.configured_memory()
        rules.initial_queue(mem)
        mem.write(0xA012, 168)
        mem.write(0xA205, 130)
        rules.next_episode(mem)
        self.assertEqual(mem.word(0xA0D0), 0xA080)
        self.assertEqual(mem.read(0xA00E), 168)

    def test_sae_progress_does_not_enable_a3_harder_flag(self):
        rules = SaeRules(fixture())
        mem = rules.configured_memory()
        mem.write(0xA012, 128)
        mem.write(0xA0D5, 255)
        rules.progress(mem)
        self.assertEqual(mem.read(0xA0D5), 0)
        self.assertEqual(mem.read(0xA035) & 16, 0)

    def test_restart_gate_suppresses_an_unwanted_scene_selection(self):
        rules = SaeRules(fixture())
        mem = rules.configured_memory()
        mem.write(0xA012, 168)
        mem.write(0xA035, 128)
        mem.write(0xA00E, 141)
        rules.select_episode(mem)
        self.assertEqual(mem.read(0xA035) & 128, 0)
        self.assertEqual(mem.read(0xA00E), 141)


class ExplicitProbabilityTest(unittest.TestCase):
    def test_external_edge_requires_an_explicit_law(self):
        decision = Decision(0, (0, 0, 0), 'automatic', Reward(),
                            (Alternative(1, 0), Alternative(2, 1)), Origin(1, 'test'), REFRESH)
        with self.assertRaisesRegex(ValueError, 'no default probability'):
            decision.expectation({1: 10, 2: 20})
        law = Distribution((Fraction(1, 4), Fraction(3, 4)), 'Synthetic test assumption')
        self.assertEqual(decision.expectation({1: 10, 2: 20}, law), Fraction(35, 2))

    def test_invalid_or_unexplained_probabilities_are_rejected(self):
        for weights, why in (((Fraction(1, 2),), 'test'), ((0.5, 0.5), 'test'),
                             ((Fraction(1, 2), Fraction(1, 2)), '')):
            with self.assertRaises(ValueError):
                Distribution(weights, why)


if __name__ == '__main__':
    unittest.main()
