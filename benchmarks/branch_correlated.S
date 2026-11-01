.option norvc
.option norelax
.include "sw/finish.inc"
.section .text
.global _start
_start:
li s0,64
        li a0,0
    1:  andi t0,s0,1
        beqz t0,2f
        addi a0,a0,1
    2:  beqz t0,3f
        addi a0,a0,1
    3:  addi s0,s0,-1
        bnez s0,1b
    sd a0,512(zero)
SIM_EXIT
dead: .word 0
