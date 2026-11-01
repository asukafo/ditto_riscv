.option norvc
.option norelax
.include "sw/finish.inc"
.section .text
.global _start
_start:
    li s0,16
    li a0,0
1:  jal ra,func
    addi s0,s0,-1
    bnez s0,1b
    sd a0,512(zero)
    SIM_EXIT
func:
    .rept 4
    addi a0,a0,1
    .endr
    ret
