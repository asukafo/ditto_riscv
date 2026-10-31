.option norvc
.option norelax
.include "sw/finish.inc"
.section .text
.global _start
_start:
    li a0,0
    li a1,0
    li a2,0
    li a3,0
    .rept 64
    addi a0,a0,1
    addi a1,a1,2
    addi a2,a2,3
    addi a3,a3,4
    .endr
    add a0,a0,a1
    add a0,a0,a2
    add a0,a0,a3
    sd a0,512(zero)
    SIM_EXIT
