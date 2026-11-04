.option norvc
.include "sw/finish.inc"
.section .text
.global _start
_start:
    addi t0, zero, -8
    srli t1, t0, 1         # logical:    0x7ffffffffffffffc
    srai t2, t0, 1         # arithmetic: 0xfffffffffffffffc (-4)
    slt t3, t0, zero       # signed -8 < 0: 1
    sltu t4, t0, zero      # unsigned 0xffff...fff8 < 0: 0
    andi t5, t0, 15        # low four bits: 8
    xori t6, t5, -1        # invert ALL 64 bits, immediate is sign extended
    addi a0, zero, 1
    slli a0, a0, 63        # 0x8000000000000000: bit 5 of shift amount matters
    addi a1, zero, 64
    srl a2, a0, a1         # rs2[5:0] = 0, result stays 0x8000000000000000
    sd t1, 512(zero)
    sd t2, 520(zero)
    sd t3, 528(zero)
    sd t4, 536(zero)
    sd t5, 544(zero)
    sd t6, 552(zero)
    sd a0, 560(zero)
    sd a2, 568(zero)
    SIM_EXIT
