#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Small original bytecode examples checking the sound potential boundaries."""

if __package__:
    from ._paths import CORE, HERE, REPO, source_path
else:
    from _paths import CORE, HERE, REPO, source_path

import unittest

from future_roms.rom_sound_rules import Cell,Rules,State,decode


def sound():
    # Synthetic two-cell program: set duration six, continue, then stop.
    # Bytecode: 10 06 20 00 00. No commercial ROM fixture is required.
    rules=object.__new__(Rules)
    rules.cells={10:Cell(10,16,6,13,False,13),13:Cell(13,0,None,None,False,15)}
    rules.roots=(10,10,10,10)
    # Literal body costs: 80/71 fetches. Last-cell F = 67 + duration;
    # first-cell F = 76 + (5*6 - 4) + (67 + 6) = 175.
    rules.coefficients={10:(0,0,175),13:(1,0,67)}
    return rules


class SoundRulesTest(unittest.TestCase):
    def test_decode_duration_and_shared_envelope_continuation_byte(self):
        cell=decode(bytes((16,6,32,0,0)),0)
        self.assertEqual(cell,Cell(0,16,6,3,False,3))
        # The mixer marker is consumed, while the envelope byte itself also
        # supplies the continuation bit. No separate envelope increment.
        cell=decode(bytes((128,128,40)),0)
        self.assertEqual(cell.following,3)
        self.assertTrue(cell.mixer)
        self.assertEqual(cell.m1,88)

    def test_decoder_rejects_truncated_payload_and_control(self):
        for image in (bytes((223,)),bytes((16,6)),bytes((0,128))):
            with self.assertRaises(ValueError):decode(image,0)

    def test_expiring_counter_has_a_different_first_difference(self):
        rules=sound();zero=State(1,10,17,0)
        self.assertEqual((rules.potential(State(1,10,17,1))-rules.potential(zero))%128,1)
        self.assertEqual((rules.potential(State(1,10,17,2))-rules.potential(State(1,10,17,1)))%128,5)
        self.assertEqual(rules.step(zero)[1],84)
        self.assertEqual(rules.step(State(1,10,17,1))[1],85)

    def test_stop_keeps_the_reload_countdown_and_other_flags(self):
        rules=sound();after,delta=rules.step(State(255,13,6,1))
        self.assertEqual(after,State(254,13,6,6))
        self.assertEqual(delta,76)
        self.assertEqual(rules.step(after),(State(254,13,6,5),9))

    def test_native_length_chirp_collapses_to_one_difference(self):
        rules=sound();after,delta=rules.advance(State(1,10,17,0),13)
        self.assertEqual(after,State(0,13,6,0))
        # 84 + five idle ticks*13 + 76 + six inactive ticks*9 = 279.
        self.assertEqual(delta,279%128)

    def test_restart_retains_duration_and_residual_countdown(self):
        rules=sound();before=State(1,13,6,4)
        after,jump=rules.start(before,0)
        self.assertEqual(after,State(1,10,6,4))
        self.assertEqual(jump,102)

    def test_large_idle_tail_needs_no_per_tick_iteration(self):
        rules=sound();after,delta=rules.advance(State(1,10,17,0),10**20)
        self.assertEqual(after,State(0,13,6,0))
        self.assertEqual(delta,47)

    def test_invalid_active_pointer_and_parameters_fail(self):
        rules=sound()
        with self.assertRaises(ValueError):rules.potential(State(1,0,0,0))
        with self.assertRaises(ValueError):rules.advance(State(0,0,0,0),-1)
        with self.assertRaises(ValueError):rules.start(State(0,0,0,0),4)
        with self.assertRaises(ValueError):State(0,0,0,256)


if __name__=='__main__':unittest.main()
