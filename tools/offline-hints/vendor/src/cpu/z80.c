#include "cpu/z80.h"

// How instructions are decoded
// ----------------------------
// Z80 opcodes have a regular structure. Split an opcode byte into fields:
//
//     bits:  7 6 | 5 4 3 | 2 1 0
//              x     y       z        and y = p:q (p = bits 5-4, q = bit 3)
//
// x picks the broad group, and y and z usually name registers or
// operations from small tables:
//
//     r[]   B C D E H L (HL) A       8-bit operands; 6 means memory at HL
//     rp[]  BC DE HL SP              16-bit register pairs
//     rp2[] BC DE HL AF              the same, for PUSH and POP
//     cc[]  NZ Z NC C PO PE P M      conditions
//     alu[] ADD ADC SUB SBC AND XOR OR CP
//
// Some opcodes are prefixes that change the next instruction:
//   CB  bit operations (rotates, shifts, BIT, SET, RES)
//   ED  extended instructions (block moves, I/O, 16-bit arithmetic, ...)
//   DD  use IX instead of HL (and (IX+d) instead of (HL))
//   FD  use IY instead of HL (and (IY+d) instead of (HL))
//
// The scheme follows "Decoding Z80 Opcodes" by Cristian Dinu, and the
// undocumented behaviour follows "The Undocumented Z80 Documented" by
// Sean Young.

enum { S = Z80_FLAG_S, Z = Z80_FLAG_Z, Y = Z80_FLAG_Y, H = Z80_FLAG_H,
       X = Z80_FLAG_X, PV = Z80_FLAG_PV, N = Z80_FLAG_N, C = Z80_FLAG_C };

// Which register stands in for HL: plain HL, or IX/IY after a DD/FD prefix.
enum { USE_HL, USE_IX, USE_IY };

// ---------------------------------------------------------------------------
// Bus access and small helpers
// ---------------------------------------------------------------------------

static uint8_t read8(Z80 *z, uint16_t addr) { return z->bus.read(z->bus.ctx, addr); }
static void write8(Z80 *z, uint16_t addr, uint8_t v) { z->bus.write(z->bus.ctx, addr, v); }

static uint16_t read16(Z80 *z, uint16_t addr)
{
    return (uint16_t)(read8(z, addr) | (read8(z, (uint16_t)(addr + 1)) << 8));
}

static void write16(Z80 *z, uint16_t addr, uint16_t v)
{
    write8(z, addr, (uint8_t)v);
    write8(z, (uint16_t)(addr + 1), (uint8_t)(v >> 8));
}

static uint8_t fetch8(Z80 *z) { return read8(z, z->pc++); }

static uint16_t fetch16(Z80 *z)
{
    uint16_t v = read16(z, z->pc);
    z->pc += 2;
    return v;
}

// Fetching an opcode (an "M1" cycle) also bumps the refresh register R.
static uint8_t fetch_opcode(Z80 *z)
{
    z->r = (uint8_t)((z->r & 0x80) | ((z->r + 1) & 0x7F));
    return fetch8(z);
}

static void push16(Z80 *z, uint16_t v)
{
    z->sp -= 2;
    write16(z, z->sp, v);
}

static uint16_t pop16(Z80 *z)
{
    uint16_t v = read16(z, z->sp);
    z->sp += 2;
    return v;
}

static uint16_t pair(uint8_t hi, uint8_t lo) { return (uint16_t)((hi << 8) | lo); }

uint16_t z80_bc(const Z80 *z) { return pair(z->b, z->c); }
uint16_t z80_de(const Z80 *z) { return pair(z->d, z->e); }
uint16_t z80_hl(const Z80 *z) { return pair(z->h, z->l); }
uint16_t z80_ix(const Z80 *z) { return pair(z->ixh, z->ixl); }
uint16_t z80_iy(const Z80 *z) { return pair(z->iyh, z->iyl); }

// All flag updates go through here, so we know the instruction touched F.
static void set_flags(Z80 *z, uint8_t f)
{
    z->f = f;
    z->flags_changed = true;
}

// S, Z and the undocumented Y and X flags, all taken from a result byte.
static uint8_t sz53(uint8_t v) { return (uint8_t)((v & (S | Y | X)) | (v ? 0 : Z)); }

// P/V set when the byte has an even number of 1 bits.
static uint8_t parity(uint8_t v)
{
    v ^= v >> 4;
    v ^= v >> 2;
    v ^= v >> 1;
    return (v & 1) ? 0 : PV;
}

static uint8_t sz53p(uint8_t v) { return sz53(v) | parity(v); }

// ---------------------------------------------------------------------------
// Registers by number, with DD/FD substitution
// ---------------------------------------------------------------------------

// r[] operand other than 6. After DD/FD, H and L become the halves of
// IX/IY (undocumented, but used by real programs).
static uint8_t *reg8(Z80 *z, int r, int idx)
{
    switch (r) {
    case 0: return &z->b;
    case 1: return &z->c;
    case 2: return &z->d;
    case 3: return &z->e;
    case 4: return idx == USE_IX ? &z->ixh : idx == USE_IY ? &z->iyh : &z->h;
    case 5: return idx == USE_IX ? &z->ixl : idx == USE_IY ? &z->iyl : &z->l;
    default: return &z->a;
    }
}

static uint16_t get_hlx(Z80 *z, int idx)
{
    return idx == USE_IX ? z80_ix(z) : idx == USE_IY ? z80_iy(z) : z80_hl(z);
}

static void set_hlx(Z80 *z, int idx, uint16_t v)
{
    uint8_t hi = (uint8_t)(v >> 8), lo = (uint8_t)v;
    if (idx == USE_IX) { z->ixh = hi; z->ixl = lo; }
    else if (idx == USE_IY) { z->iyh = hi; z->iyl = lo; }
    else { z->h = hi; z->l = lo; }
}

static uint16_t get_rp(Z80 *z, int p, int idx)
{
    switch (p) {
    case 0: return z80_bc(z);
    case 1: return z80_de(z);
    case 2: return get_hlx(z, idx);
    default: return z->sp;
    }
}

static void set_rp(Z80 *z, int p, int idx, uint16_t v)
{
    switch (p) {
    case 0: z->b = (uint8_t)(v >> 8); z->c = (uint8_t)v; break;
    case 1: z->d = (uint8_t)(v >> 8); z->e = (uint8_t)v; break;
    case 2: set_hlx(z, idx, v); break;
    default: z->sp = v; break;
    }
}

// rp2[]: like rp[], but 3 means AF (for PUSH and POP).
static uint16_t get_rp2(Z80 *z, int p, int idx)
{
    return p == 3 ? pair(z->a, z->f) : get_rp(z, p, idx);
}

static void set_rp2(Z80 *z, int p, int idx, uint16_t v)
{
    if (p == 3) {
        z->a = (uint8_t)(v >> 8);
        z->f = (uint8_t)v;
    } else {
        set_rp(z, p, idx, v);
    }
}

// The address of a memory operand: (HL), or (IX+d) / (IY+d), where the
// signed displacement d is the next byte of the instruction.
static uint16_t operand_addr(Z80 *z, int idx)
{
    if (idx == USE_HL) return z80_hl(z);
    int8_t d = (int8_t)fetch8(z);
    z->wz = (uint16_t)(get_hlx(z, idx) + d);
    return z->wz;
}

static bool condition(Z80 *z, int cc)
{
    switch (cc) {
    case 0: return !(z->f & Z);
    case 1: return z->f & Z;
    case 2: return !(z->f & C);
    case 3: return z->f & C;
    case 4: return !(z->f & PV);
    case 5: return z->f & PV;
    case 6: return !(z->f & S);
    default: return z->f & S;
    }
}

// ---------------------------------------------------------------------------
// Arithmetic and logic
// ---------------------------------------------------------------------------

static void add8(Z80 *z, uint8_t v, int carry)
{
    unsigned a = z->a, r = a + v + (unsigned)carry;
    set_flags(z, sz53((uint8_t)r) | ((a ^ v ^ r) & H) |
                 (((a ^ ~v) & (a ^ r) & 0x80) ? PV : 0) | (r > 0xFF ? C : 0));
    z->a = (uint8_t)r;
}

// Subtraction; returns the result without storing it (CP discards it).
static uint8_t sub8(Z80 *z, uint8_t v, int carry)
{
    unsigned a = z->a, r = a - v - (unsigned)carry;
    set_flags(z, sz53((uint8_t)r) | ((a ^ v ^ r) & H) | N |
                 (((a ^ v) & (a ^ r) & 0x80) ? PV : 0) | ((r >> 8) & C));
    return (uint8_t)r;
}

static void alu(Z80 *z, int op, uint8_t v)
{
    switch (op) {
    case 0: add8(z, v, 0); break;
    case 1: add8(z, v, z->f & C); break;
    case 2: z->a = sub8(z, v, 0); break;
    case 3: z->a = sub8(z, v, z->f & C); break;
    case 4: z->a &= v; set_flags(z, sz53p(z->a) | H); break;
    case 5: z->a ^= v; set_flags(z, sz53p(z->a)); break;
    case 6: z->a |= v; set_flags(z, sz53p(z->a)); break;
    default:
        // CP is a subtraction that only keeps the flags. Oddly, Y and X
        // come from the operand rather than the result.
        sub8(z, v, 0);
        set_flags(z, (uint8_t)((z->f & ~(Y | X)) | (v & (Y | X))));
        break;
    }
}

static uint8_t inc8(Z80 *z, uint8_t v)
{
    uint8_t r = (uint8_t)(v + 1);
    set_flags(z, (z->f & C) | sz53(r) | ((r & 0x0F) == 0 ? H : 0) | (r == 0x80 ? PV : 0));
    return r;
}

static uint8_t dec8(Z80 *z, uint8_t v)
{
    uint8_t r = (uint8_t)(v - 1);
    set_flags(z, (z->f & C) | sz53(r) | N | ((v & 0x0F) == 0 ? H : 0) | (r == 0x7F ? PV : 0));
    return r;
}

static uint16_t add16(Z80 *z, uint16_t a, uint16_t b)
{
    uint32_t r = (uint32_t)a + b;
    z->wz = (uint16_t)(a + 1);
    set_flags(z, (z->f & (S | Z | PV)) | (((a ^ b ^ r) >> 8) & H) |
                 ((r >> 8) & (Y | X)) | (r > 0xFFFF ? C : 0));
    return (uint16_t)r;
}

static uint16_t adc16(Z80 *z, uint16_t a, uint16_t b)
{
    uint32_t r = (uint32_t)a + b + (z->f & C);
    z->wz = (uint16_t)(a + 1);
    set_flags(z, ((r >> 8) & (S | Y | X)) | ((r & 0xFFFF) ? 0 : Z) |
                 (((a ^ b ^ r) >> 8) & H) |
                 (((a ^ ~b) & (a ^ r) & 0x8000) ? PV : 0) | ((r >> 16) & C));
    return (uint16_t)r;
}

static uint16_t sbc16(Z80 *z, uint16_t a, uint16_t b)
{
    uint32_t r = (uint32_t)a - b - (z->f & C);
    z->wz = (uint16_t)(a + 1);
    set_flags(z, ((r >> 8) & (S | Y | X)) | ((r & 0xFFFF) ? 0 : Z) |
                 (((a ^ b ^ r) >> 8) & H) | N |
                 (((a ^ b) & (a ^ r) & 0x8000) ? PV : 0) | ((r >> 16) & C));
    return (uint16_t)r;
}

// CB-prefixed rotates and shifts: RLC RRC RL RR SLA SRA SLL SRL.
// (SLL is undocumented: shift left and set bit 0.)
static uint8_t rotate(Z80 *z, int op, uint8_t v)
{
    uint8_t r, carry;
    switch (op) {
    case 0: carry = v >> 7; r = (uint8_t)((v << 1) | carry); break;
    case 1: carry = v & 1; r = (uint8_t)((v >> 1) | (carry << 7)); break;
    case 2: carry = v >> 7; r = (uint8_t)((v << 1) | (z->f & C)); break;
    case 3: carry = v & 1; r = (uint8_t)((v >> 1) | ((z->f & C) << 7)); break;
    case 4: carry = v >> 7; r = (uint8_t)(v << 1); break;
    case 5: carry = v & 1; r = (uint8_t)((v >> 1) | (v & 0x80)); break;
    case 6: carry = v >> 7; r = (uint8_t)((v << 1) | 1); break;
    default: carry = v & 1; r = v >> 1; break;
    }
    set_flags(z, sz53p(r) | carry);
    return r;
}

// BIT b,v. The undocumented Y and X flags come from xy: the value itself
// for registers, but for memory operands a byte of the internal WZ register.
static void bit_test(Z80 *z, int b, uint8_t v, uint8_t xy)
{
    uint8_t f = (z->f & C) | H | (xy & (Y | X));
    if (!(v & (1 << b))) f |= Z | PV;
    if (b == 7 && (v & 0x80)) f |= S;
    set_flags(z, f);
}

// Decimal adjust: fix A after adding or subtracting binary-coded decimal.
static void daa(Z80 *z)
{
    uint8_t a = z->a, f = z->f, diff = 0, carry = f & C;
    if ((f & H) || (a & 0x0F) > 9) diff |= 0x06;
    if (carry || a > 0x99) {
        diff |= 0x60;
        carry = C;
    }
    uint8_t r, half;
    if (f & N) {
        r = (uint8_t)(a - diff);
        half = ((f & H) && (a & 0x0F) < 6) ? H : 0;
    } else {
        r = (uint8_t)(a + diff);
        half = (a & 0x0F) > 9 ? H : 0;
    }
    z->a = r;
    set_flags(z, sz53p(r) | half | (f & N) | carry);
}

// ---------------------------------------------------------------------------
// CB prefix: rotates, shifts and bit operations
// ---------------------------------------------------------------------------

static int exec_cb(Z80 *z, int idx)
{
    uint16_t addr = 0;
    uint8_t op;
    if (idx == USE_HL) {
        op = fetch_opcode(z);
    } else {
        // DD CB d op: the displacement comes before the opcode, and the
        // opcode fetch doesn't count as an M1 cycle.
        addr = operand_addr(z, idx);
        op = fetch8(z);
    }
    int x = op >> 6, y = (op >> 3) & 7, r = op & 7;
    bool memory = idx != USE_HL || r == 6;
    if (memory && idx == USE_HL) addr = z80_hl(z);

    uint8_t v = memory ? read8(z, addr) : *reg8(z, r, USE_HL);
    uint8_t result;
    switch (x) {
    case 0: result = rotate(z, y, v); break;
    case 1:
        bit_test(z, y, v, memory ? (uint8_t)(z->wz >> 8) : v);
        if (idx != USE_HL) return 16;
        return memory ? 12 : 8;
    case 2: result = v & (uint8_t)~(1 << y); break;
    default: result = v | (uint8_t)(1 << y); break;
    }

    if (memory) {
        write8(z, addr, result);
        // Undocumented: DD CB d op with a register field also copies the
        // result into that register.
        if (idx != USE_HL && r != 6) *reg8(z, r, USE_HL) = result;
        return idx != USE_HL ? 19 : 15;
    }
    *reg8(z, r, USE_HL) = result;
    return 8;
}

// ---------------------------------------------------------------------------
// ED prefix: extended instructions
// ---------------------------------------------------------------------------

static uint8_t port_in(Z80 *z, uint16_t port) { return z->bus.in(z->bus.ctx, port); }
static void port_out(Z80 *z, uint16_t port, uint8_t v) { z->bus.out(z->bus.ctx, port, v); }

// Block instructions: LDI/LDD/LDIR/LDDR, CPI..., INI..., OUTI...
// dir is +1 or -1; repeat is true for the ...R forms.
static int block_op(Z80 *z, int kind, int dir, bool repeat)
{
    uint16_t hl = z80_hl(z), bc = z80_bc(z);
    bool again = false;

    switch (kind) {
    case 0: {  // LDI / LDD: copy (HL) to (DE)
        uint8_t v = read8(z, hl);
        uint16_t de = z80_de(z);
        write8(z, de, v);
        set_rp(z, 1, USE_HL, (uint16_t)(de + dir));
        set_rp(z, 2, USE_HL, (uint16_t)(hl + dir));
        set_rp(z, 0, USE_HL, --bc);
        uint8_t n = (uint8_t)(v + z->a);
        set_flags(z, (z->f & (S | Z | C)) | (bc ? PV : 0) | (n & X) | ((n & 0x02) << 4));
        again = bc != 0;
        break;
    }
    case 1: {  // CPI / CPD: compare A with (HL)
        uint8_t v = read8(z, hl);
        uint8_t r = (uint8_t)(z->a - v);
        uint8_t half = (z->a ^ v ^ r) & H;
        uint8_t n = (uint8_t)(r - (half ? 1 : 0));
        set_rp(z, 2, USE_HL, (uint16_t)(hl + dir));
        set_rp(z, 0, USE_HL, --bc);
        z->wz = (uint16_t)(z->wz + dir);
        set_flags(z, (z->f & C) | N | (r & S) | (r ? 0 : Z) | half | (bc ? PV : 0) |
                     (n & X) | ((n & 0x02) << 4));
        again = bc != 0 && r != 0;
        break;
    }
    case 2: {  // INI / IND: read port (C) into (HL)
        uint8_t v = port_in(z, bc);
        z->wz = (uint16_t)(bc + dir);
        z->b--;
        write8(z, hl, v);
        set_rp(z, 2, USE_HL, (uint16_t)(hl + dir));
        unsigned k = v + (uint8_t)(z->c + dir);
        set_flags(z, sz53(z->b) | ((v & 0x80) ? N : 0) | (k > 0xFF ? H | C : 0) |
                     parity((uint8_t)((k & 7) ^ z->b)));
        again = z->b != 0;
        break;
    }
    default: {  // OUTI / OUTD: write (HL) to port (C)
        uint8_t v = read8(z, hl);
        z->b--;
        z->wz = (uint16_t)(z80_bc(z) + dir);
        port_out(z, z80_bc(z), v);
        set_rp(z, 2, USE_HL, (uint16_t)(hl + dir));
        unsigned k = v + z->l;
        set_flags(z, sz53(z->b) | ((v & 0x80) ? N : 0) | (k > 0xFF ? H | C : 0) |
                     parity((uint8_t)((k & 7) ^ z->b)));
        again = z->b != 0;
        break;
    }
    }

    if (repeat && again) {
        z->pc -= 2;  // run this instruction again
        z->wz = (uint16_t)(z->pc + 1);
        return 21;
    }
    return 16;
}

static int exec_ed(Z80 *z)
{
    uint8_t op = fetch_opcode(z);
    int x = op >> 6, y = (op >> 3) & 7, r = op & 7, p = y >> 1, q = y & 1;

    if (x == 2 && r <= 3 && y >= 4)
        return block_op(z, r, (y & 1) ? -1 : 1, y >= 6);
    if (x != 1) return 8;  // everything else in ED is a do-nothing

    switch (r) {
    case 0: {  // IN r,(C); with r=6 only the flags are kept
        uint8_t v = port_in(z, z80_bc(z));
        z->wz = (uint16_t)(z80_bc(z) + 1);
        if (y != 6) *reg8(z, y, USE_HL) = v;
        set_flags(z, (z->f & C) | sz53p(v));
        return 12;
    }
    case 1:  // OUT (C),r; with r=6 outputs 0
        port_out(z, z80_bc(z), y == 6 ? 0 : *reg8(z, y, USE_HL));
        z->wz = (uint16_t)(z80_bc(z) + 1);
        return 12;
    case 2: {
        uint16_t hl = z80_hl(z), v = get_rp(z, p, USE_HL);
        set_rp(z, 2, USE_HL, q ? adc16(z, hl, v) : sbc16(z, hl, v));
        return 15;
    }
    case 3: {
        uint16_t addr = fetch16(z);
        if (q) set_rp(z, p, USE_HL, read16(z, addr));
        else write16(z, addr, get_rp(z, p, USE_HL));
        z->wz = (uint16_t)(addr + 1);
        return 20;
    }
    case 4: {  // NEG
        uint8_t v = z->a;
        z->a = 0;
        z->a = sub8(z, v, 0);
        return 8;
    }
    case 5:  // RETN / RETI
        z->pc = pop16(z);
        z->wz = z->pc;
        z->iff1 = z->iff2;
        return 14;
    case 6: {
        static const uint8_t modes[8] = {0, 0, 1, 2, 0, 0, 1, 2};
        z->im = modes[y];
        return 8;
    }
    default:
        switch (y) {
        case 0: z->i = z->a; return 9;
        case 1: z->r = z->a; return 9;
        case 2:
        case 3:  // LD A,I / LD A,R: P/V shows whether interrupts are enabled
            z->a = y == 2 ? z->i : z->r;
            set_flags(z, (z->f & C) | sz53(z->a) | (z->iff2 ? PV : 0));
            return 9;
        case 4:
        case 5: {  // RRD / RLD: rotate BCD digits between A and (HL)
            uint16_t hl = z80_hl(z);
            uint8_t v = read8(z, hl);
            if (y == 4) {
                write8(z, hl, (uint8_t)((z->a << 4) | (v >> 4)));
                z->a = (z->a & 0xF0) | (v & 0x0F);
            } else {
                write8(z, hl, (uint8_t)((v << 4) | (z->a & 0x0F)));
                z->a = (z->a & 0xF0) | (v >> 4);
            }
            z->wz = (uint16_t)(hl + 1);
            set_flags(z, (z->f & C) | sz53p(z->a));
            return 18;
        }
        default: return 8;
        }
    }
}

// ---------------------------------------------------------------------------
// Unprefixed instructions (and their DD/FD variants)
// ---------------------------------------------------------------------------
//
// T-state counts returned here are for the plain instruction; a DD or FD
// prefix adds 4 more, counted by the caller. Forms that use (IX+d) add the
// extra time for the displacement here.

static int exec_main(Z80 *z, uint8_t op, int idx)
{
    int x = op >> 6, y = (op >> 3) & 7, r = op & 7, p = y >> 1, q = y & 1;
    bool indexed = idx != USE_HL;

    switch (x) {
    case 0:
        switch (r) {
        case 0:
            switch (y) {
            case 0: return 4;  // NOP
            case 1: {          // EX AF,AF'
                uint8_t a = z->a, f = z->f;
                z->a = z->a2; z->f = z->f2;
                z->a2 = a; z->f2 = f;
                return 4;
            }
            case 2: {  // DJNZ d
                int8_t d = (int8_t)fetch8(z);
                if (--z->b) {
                    z->pc = (uint16_t)(z->pc + d);
                    z->wz = z->pc;
                    return 13;
                }
                return 8;
            }
            default: {  // JR d, JR cc,d
                int8_t d = (int8_t)fetch8(z);
                if (y == 3 || condition(z, y - 4)) {
                    z->pc = (uint16_t)(z->pc + d);
                    z->wz = z->pc;
                    return 12;
                }
                return 7;
            }
            }
        case 1:
            if (q == 0) {  // LD rp,nn
                set_rp(z, p, idx, fetch16(z));
                return 10;
            }
            set_hlx(z, idx, add16(z, get_hlx(z, idx), get_rp(z, p, idx)));  // ADD HL,rp
            return 11;
        case 2: {
            uint16_t addr;
            switch (y) {
            case 0:  // LD (BC),A
            case 2:  // LD (DE),A
                addr = y == 0 ? z80_bc(z) : z80_de(z);
                write8(z, addr, z->a);
                z->wz = (uint16_t)((z->a << 8) | ((addr + 1) & 0xFF));
                return 7;
            case 1:  // LD A,(BC)
            case 3:  // LD A,(DE)
                addr = y == 1 ? z80_bc(z) : z80_de(z);
                z->a = read8(z, addr);
                z->wz = (uint16_t)(addr + 1);
                return 7;
            case 4:  // LD (nn),HL
                addr = fetch16(z);
                write16(z, addr, get_hlx(z, idx));
                z->wz = (uint16_t)(addr + 1);
                return 16;
            case 5:  // LD HL,(nn)
                addr = fetch16(z);
                set_hlx(z, idx, read16(z, addr));
                z->wz = (uint16_t)(addr + 1);
                return 16;
            case 6:  // LD (nn),A
                addr = fetch16(z);
                write8(z, addr, z->a);
                z->wz = (uint16_t)((z->a << 8) | ((addr + 1) & 0xFF));
                return 13;
            default:  // LD A,(nn)
                addr = fetch16(z);
                z->a = read8(z, addr);
                z->wz = (uint16_t)(addr + 1);
                return 13;
            }
        }
        case 3:  // INC rp / DEC rp (no flags)
            set_rp(z, p, idx, (uint16_t)(get_rp(z, p, idx) + (q ? -1 : 1)));
            return 6;
        case 4:  // INC r
        case 5:  // DEC r
            if (y == 6) {
                uint16_t addr = operand_addr(z, idx);
                uint8_t v = read8(z, addr);
                write8(z, addr, r == 4 ? inc8(z, v) : dec8(z, v));
                return indexed ? 19 : 11;
            } else {
                uint8_t *reg = reg8(z, y, idx);
                *reg = r == 4 ? inc8(z, *reg) : dec8(z, *reg);
                return 4;
            }
        case 6:  // LD r,n
            if (y == 6) {
                uint16_t addr = operand_addr(z, idx);  // displacement comes first
                write8(z, addr, fetch8(z));
                return indexed ? 15 : 10;
            }
            *reg8(z, y, idx) = fetch8(z);
            return 7;
        default: {
            uint8_t a = z->a, f = z->f, keep = f & (S | Z | PV);
            switch (y) {
            case 0:  // RLCA
                z->a = (uint8_t)((a << 1) | (a >> 7));
                set_flags(z, keep | (z->a & (Y | X)) | (a >> 7));
                break;
            case 1:  // RRCA
                z->a = (uint8_t)((a >> 1) | (a << 7));
                set_flags(z, keep | (z->a & (Y | X)) | (a & 1));
                break;
            case 2:  // RLA
                z->a = (uint8_t)((a << 1) | (f & C));
                set_flags(z, keep | (z->a & (Y | X)) | (a >> 7));
                break;
            case 3:  // RRA
                z->a = (uint8_t)((a >> 1) | ((f & C) << 7));
                set_flags(z, keep | (z->a & (Y | X)) | (a & 1));
                break;
            case 4: daa(z); break;
            case 5:  // CPL
                z->a = (uint8_t)~a;
                set_flags(z, (f & (S | Z | PV | C)) | H | N | (z->a & (Y | X)));
                break;
            case 6:  // SCF. Y and X depend on whether the previous
                     // instruction changed the flags (the "Q" quirk).
                set_flags(z, keep | C | (((z->q ^ f) | a) & (Y | X)));
                break;
            default:  // CCF
                set_flags(z, keep | ((f & C) ? H : 0) | ((f & C) ^ C) |
                             (((z->q ^ f) | a) & (Y | X)));
                break;
            }
            return 4;
        }
        }

    case 1:  // LD r,r'  (and HALT, where LD (HL),(HL) would be)
        if (y == 6 && r == 6) {
            z->halted = true;
            return 4;
        }
        if (r == 6) {  // LD r,(HL): r is always a plain register
            uint16_t addr = operand_addr(z, idx);
            *reg8(z, y, USE_HL) = read8(z, addr);
            return indexed ? 15 : 7;
        }
        if (y == 6) {  // LD (HL),r
            uint16_t addr = operand_addr(z, idx);
            write8(z, addr, *reg8(z, r, USE_HL));
            return indexed ? 15 : 7;
        }
        *reg8(z, y, idx) = *reg8(z, r, idx);
        return 4;

    case 2:  // ALU A,r
        if (r == 6) {
            alu(z, y, read8(z, operand_addr(z, idx)));
            return indexed ? 15 : 7;
        }
        alu(z, y, *reg8(z, r, idx));
        return 4;

    default:
        switch (r) {
        case 0:  // RET cc
            if (condition(z, y)) {
                z->pc = pop16(z);
                z->wz = z->pc;
                return 11;
            }
            return 5;
        case 1:
            if (q == 0) {  // POP rp2
                set_rp2(z, p, idx, pop16(z));
                return 10;
            }
            switch (p) {
            case 0:  // RET
                z->pc = pop16(z);
                z->wz = z->pc;
                return 10;
            case 1: {  // EXX
                uint8_t t;
                t = z->b; z->b = z->b2; z->b2 = t;
                t = z->c; z->c = z->c2; z->c2 = t;
                t = z->d; z->d = z->d2; z->d2 = t;
                t = z->e; z->e = z->e2; z->e2 = t;
                t = z->h; z->h = z->h2; z->h2 = t;
                t = z->l; z->l = z->l2; z->l2 = t;
                return 4;
            }
            case 2:  // JP (HL)
                z->pc = get_hlx(z, idx);
                return 4;
            default:  // LD SP,HL
                z->sp = get_hlx(z, idx);
                return 6;
            }
        case 2: {  // JP cc,nn
            uint16_t addr = fetch16(z);
            z->wz = addr;
            if (condition(z, y)) z->pc = addr;
            return 10;
        }
        case 3:
            switch (y) {
            case 0:  // JP nn
                z->pc = fetch16(z);
                z->wz = z->pc;
                return 10;
            case 1:  // CB prefix: handled before we get here
                return 4;
            case 2: {  // OUT (n),A: the port's high byte comes from A
                uint8_t n = fetch8(z);
                port_out(z, (uint16_t)((z->a << 8) | n), z->a);
                z->wz = (uint16_t)((z->a << 8) | ((n + 1) & 0xFF));
                return 11;
            }
            case 3: {  // IN A,(n)
                uint16_t port = (uint16_t)((z->a << 8) | fetch8(z));
                z->a = port_in(z, port);
                z->wz = (uint16_t)(port + 1);
                return 11;
            }
            case 4: {  // EX (SP),HL
                uint16_t v = read16(z, z->sp);
                write16(z, z->sp, get_hlx(z, idx));
                set_hlx(z, idx, v);
                z->wz = v;
                return 19;
            }
            case 5: {  // EX DE,HL (never affected by DD/FD)
                uint8_t t;
                t = z->d; z->d = z->h; z->h = t;
                t = z->e; z->e = z->l; z->l = t;
                return 4;
            }
            case 6:  // DI
                z->iff1 = z->iff2 = false;
                return 4;
            default:  // EI: takes effect after the next instruction
                z->iff1 = z->iff2 = true;
                z->ei_pending = true;
                return 4;
            }
        case 4: {  // CALL cc,nn
            uint16_t addr = fetch16(z);
            z->wz = addr;
            if (condition(z, y)) {
                push16(z, z->pc);
                z->pc = addr;
                return 17;
            }
            return 10;
        }
        case 5:
            if (q == 0) {  // PUSH rp2
                push16(z, get_rp2(z, p, idx));
                return 11;
            }
            // CALL nn (p == 0); DD, ED and FD prefixes are handled earlier.
            {
                uint16_t addr = fetch16(z);
                z->wz = addr;
                push16(z, z->pc);
                z->pc = addr;
                return 17;
            }
        case 6:  // ALU A,n
            alu(z, y, fetch8(z));
            return 7;
        default:  // RST
            push16(z, z->pc);
            z->pc = (uint16_t)(y * 8);
            z->wz = z->pc;
            return 11;
        }
    }
}

// ---------------------------------------------------------------------------
// Interrupts and the main step
// ---------------------------------------------------------------------------

static void bump_r(Z80 *z)
{
    z->r = (uint8_t)((z->r & 0x80) | ((z->r + 1) & 0x7F));
}

// Respond to a pending interrupt, if any. Returns T-states used, or 0.
static int take_interrupt(Z80 *z)
{
    if (z->nmi) {
        // Non-maskable: always taken. IFF2 remembers whether maskable
        // interrupts were on, so RETN can restore them.
        z->nmi = false;
        z->halted = false;
        z->iff1 = false;
        bump_r(z);
        push16(z, z->pc);
        z->pc = 0x0066;
        z->wz = z->pc;
        return 11;
    }
    if (!z->irq || !z->iff1 || z->ei_pending) return 0;

    z->halted = false;
    z->iff1 = z->iff2 = false;
    z->irq_taken = true;
    bump_r(z);
    switch (z->im) {
    case 2:  // jump through a table: address from (I * 256 + data byte)
        push16(z, z->pc);
        z->pc = read16(z, (uint16_t)((z->i << 8) | z->irq_data));
        z->wz = z->pc;
        return 19;
    case 1:  // always RST 38h
        push16(z, z->pc);
        z->pc = 0x0038;
        z->wz = z->pc;
        return 13;
    default:
        // Mode 0 executes whatever instruction the device puts on the bus.
        // In practice that's an RST, which is all we support.
        push16(z, z->pc);
        z->pc = z->irq_data & 0x38;
        z->wz = z->pc;
        return 13;
    }
}

static int execute(Z80 *z)
{
    uint8_t op = fetch_opcode(z);
    int idx = USE_HL, cycles = 0;
    while (op == 0xDD || op == 0xFD) {  // the last prefix wins
        idx = op == 0xDD ? USE_IX : USE_IY;
        cycles += 4;
        op = fetch_opcode(z);
    }
    if (op == 0xED) return cycles + exec_ed(z);  // ED ignores DD/FD
    if (op == 0xCB) return cycles + exec_cb(z, idx);
    return cycles + exec_main(z, op, idx);
}

int z80_step(Z80 *z)
{
    int cycles = take_interrupt(z);
    if (cycles) {
        z->q = 0;
        return cycles;
    }
    z->ei_pending = false;

    if (z->halted) {  // HALT keeps refreshing memory, doing nothing else
        bump_r(z);
        return 4;
    }

    z->flags_changed = false;
    cycles = execute(z);
    z->q = z->flags_changed ? z->f : 0;
    return cycles;
}

void z80_reset(Z80 *z)
{
    z->pc = 0;
    z->sp = 0xFFFF;
    z->a = z->f = 0xFF;
    z->i = z->r = 0;
    z->wz = 0;
    z->iff1 = z->iff2 = false;
    z->im = 0;
    z->halted = false;
    z->ei_pending = false;
    z->nmi = false;
    z->q = 0;
}

void z80_init(Z80 *z, Z80Bus bus)
{
    *z = (Z80){.bus = bus};
    z80_reset(z);
}
