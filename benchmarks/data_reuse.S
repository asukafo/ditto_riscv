.option norvc
.option norelax
.include "sw/finish.inc"
.section .text
.global _start
_start:
    li t0,0x3000
    li t1,128
    li a0,0
1:  ld t2,0(t0)
    add a0,a0,t2
    addi t1,t1,-1
    bnez t1,1b
    sd a0,512(zero)
    SIM_EXIT
.org 0x3000
.dword 7,11
