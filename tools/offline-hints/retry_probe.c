/* SPDX-License-Identifier: GPL-3.0-or-later
 * Test-only real-ROM replay: deliberately miss windows, then resume the oracle.
 * RAM snapshots go only to the test runner, never into an APK or hint file.
 */
#define main extractor_main
#include "extract.c"
#undef main

int main(int argc, char **argv) {
    if (argc != 5) return 2;
    int fail_after = atoi(argv[3]), fail_count = atoi(argv[4]);
    if (fail_after < 1 || fail_after > 200 || fail_count < 1 || fail_count > 3) return 2;
    Machine root = {0};
    if (!cine_load_roms(&root.board, argv[1])) return 1;
    bool dle = !strcmp(argv[2], "dle21");
    if (dle) memset(root.board.rom + 0x6000, 0, 0x4000);
    ldp_init(&root.ldp, 24000.0/1001.0, 0);
    ldv1000_init(&root.player, &root.ldp, CINE_CPU_HZ);
    cine_reset(&root.board, cine_ldv1000_link(&root.player));
    root.board.dsw1 = dle ? 0x32 : 0x3d;
    root.board.dsw2 = dle ? 0xd8 : 0xee;
    while (root.board.cycles < (uint64_t)(68.2 * CINE_CPU_HZ)) {
        root.board.inputs.start1 = root.board.cycles >= 68 * UINT64_C(4000000);
        root.board.inputs.ace = root.board.inputs.start1;
        run_until(&root, root.board.cycles + SLICE_CYCLES);
    }
    memset(&root.board.inputs, 0, sizeof root.board.inputs);
    CineAutoplay ap; cine_autoplay_init(&ap, false);
    bool missing = false;
    int moves = 0, life_moves = 0, lost = 0, initial = lives(&root.board), after = 0;
    while (root.board.cycles < 1200 * UINT64_C(4000000) && after < 40) {
        if (!missing && lost < fail_count && life_moves >= fail_after && ap.pressing < 0) {
            cine_autoplay_free(&ap); cine_autoplay_init(&ap, false);
            memset(&root.board.inputs, 0, sizeof root.board.inputs);
            missing = true;
        }
        if (missing && lives(&root.board) < initial) {
            ++lost; initial = lives(&root.board); life_moves = 0; missing = false;
            printf("DEATH %d %d %d\n", lost, initial, root.ldp.frame);
        }
        int before = ap.moves_made;
        if (!missing) cine_autoplay_play(&ap, &root.board, &root.ldp, &root.player);
        if (ap.moves_made > before) {
            ++moves; ++life_moves;
            if (lost == fail_count) ++after;
            printf("SNAP %d %d %d %d ", moves, lives(&root.board), root.ldp.frame, ap.pressing);
            for (unsigned i=0;i<sizeof root.board.ram;i++) printf("%02x",root.board.ram[i]);
            puts("");
        }
        uint64_t next=cine_autoplay_next_event(&ap), slice=SLICE_CYCLES;
        if(next>root.board.cycles && next-root.board.cycles<slice) slice=next-root.board.cycles;
        run_until(&root,root.board.cycles+slice);
    }
    cine_autoplay_free(&ap);
    return lost == fail_count && after == 40 ? 0 : 3;
}
