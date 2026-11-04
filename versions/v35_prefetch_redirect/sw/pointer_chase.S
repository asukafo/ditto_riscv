.option norvc
.include "sw/finish.inc"
.section .text
.global _start
_start:
    lui t0, 1
    addi t1, zero, 64
    addi t2, zero, 0
loop:
    ld t3, 8(t0)
    ld t0, 0(t0)
    add t2, t2, t3
    addi t1, t1, -1
    bne t1, zero, loop
    sd t2, 512(zero)
    SIM_EXIT
.org 0x1000
.incbin "build/pointers.bin"
