// z80.h - a Zilog Z80 CPU emulator.
//
// The Z80 (1976) is an 8-bit CPU found in countless computers and arcade
// boards; Dragon's Lair runs on one at about 4 MHz. This emulator runs one
// instruction at a time and reports how many clock cycles ("T-states") it
// took, so the caller can keep the CPU in step with the rest of the board.
//
// The CPU talks to the outside world through four functions: reading and
// writing memory, and reading and writing I/O ports (the Z80 has a separate
// 256-port I/O space, used by IN and OUT instructions). The board supplies
// these, which is where ROMs, RAM and hardware devices get wired up.
//
// The emulator covers the whole instruction set, including the undocumented
// instructions and flag bits that real software sometimes relies on.

#ifndef LV_Z80_H
#define LV_Z80_H

#include <stdbool.h>
#include <stdint.h>

typedef struct {
    void *ctx;  // passed back to every function, e.g. the board
    uint8_t (*read)(void *ctx, uint16_t addr);
    void (*write)(void *ctx, uint16_t addr, uint8_t value);
    uint8_t (*in)(void *ctx, uint16_t port);
    void (*out)(void *ctx, uint16_t port, uint8_t value);
} Z80Bus;

// Flag bits in the F register.
enum {
    Z80_FLAG_C = 0x01,   // carry
    Z80_FLAG_N = 0x02,   // last operation was a subtraction (for DAA)
    Z80_FLAG_PV = 0x04,  // parity (logic ops) or overflow (arithmetic)
    Z80_FLAG_X = 0x08,   // undocumented: copy of bit 3 of a result
    Z80_FLAG_H = 0x10,   // half carry (carry out of bit 3, for DAA)
    Z80_FLAG_Y = 0x20,   // undocumented: copy of bit 5 of a result
    Z80_FLAG_Z = 0x40,   // zero
    Z80_FLAG_S = 0x80,   // sign (bit 7 of the result)
};

typedef struct {
    // Main registers. They pair up as BC, DE, HL and AF for 16-bit work.
    uint8_t a, f, b, c, d, e, h, l;
    // The alternate set, swapped in by EX AF,AF' and EXX.
    uint8_t a2, f2, b2, c2, d2, e2, h2, l2;
    // Index registers, kept as byte halves because undocumented
    // instructions can use IXH, IXL, IYH and IYL on their own.
    uint8_t ixh, ixl, iyh, iyl;
    uint16_t sp, pc;
    uint8_t i;   // interrupt vector base (interrupt mode 2)
    uint8_t r;   // memory refresh counter; its low 7 bits count fetches
    uint16_t wz; // internal temporary register ("MEMPTR"); leaks into flags

    bool iff1, iff2;  // interrupt enable flip-flops
    uint8_t im;       // interrupt mode: 0, 1 or 2
    bool halted;      // executing HALT: idle until an interrupt

    // Interrupt inputs, set by the board.
    bool irq;           // maskable interrupt line held active
    uint8_t irq_data;   // byte the interrupting device puts on the data bus
    bool nmi;           // non-maskable interrupt requested (edge)
    bool irq_taken;     // set when the CPU accepts a maskable interrupt, so
                        // a board that holds the line until then can let go

    // Internal bookkeeping.
    bool ei_pending;    // EI was just executed: interrupts wait one instruction
    uint8_t q;          // F if the last instruction changed flags, else 0
    bool flags_changed; // set while an instruction writes F

    Z80Bus bus;
} Z80;

// Set up a CPU connected to the given bus, then reset it.
void z80_init(Z80 *cpu, Z80Bus bus);

// Reset: PC=0, interrupts off, interrupt mode 0.
void z80_reset(Z80 *cpu);

// Run one instruction (or respond to an interrupt). Returns T-states used.
int z80_step(Z80 *cpu);

// 16-bit register pairs.
uint16_t z80_bc(const Z80 *cpu);
uint16_t z80_de(const Z80 *cpu);
uint16_t z80_hl(const Z80 *cpu);
uint16_t z80_ix(const Z80 *cpu);
uint16_t z80_iy(const Z80 *cpu);

#endif
