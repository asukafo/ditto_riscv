.option norvc
.option norelax
.include "sw/finish.inc"
.section .text
.global _start
_start:

        li s0,32
        li a0,0
        j A
        .balign 64
    A:  beq zero,zero,B
        .word 0
        .balign 64
    B:  bne zero,zero,dead
        addi a0,a0,1
        addi s0,s0,-1
        bnez s0,A
    sd a0,512(zero)
SIM_EXIT
dead: .word 0
