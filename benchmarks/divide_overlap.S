.option norvc
.option norelax
.include "sw/finish.inc"
.section .text
.global _start
_start:
    li s0,4
    li a0,0
    li a1,1000
    li a2,7
1:  div t0,a1,a2
    .rept 12
    addi a0,a0,1
    .endr
    addi s0,s0,-1
    bnez s0,1b
    sd t0,520(zero)
    sd a0,512(zero)
    SIM_EXIT
