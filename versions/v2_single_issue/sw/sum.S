.option norvc
.include "sw/finish.inc"
.section .text
.global _start
_start:
    lui t0, 1
    addi t1, zero, 64
    addi t2, zero, 0
loop:
    ld t3, 0(t0)
    add t2, t2, t3
    addi t0, t0, 8
    addi t1, t1, -1
    bne t1, zero, loop
    sd t2, 512(zero)
    SIM_EXIT
.org 0x1000
.set value, 1
.rept 64
    .dword value
    .set value, value+1
.endr
