.option rvc
.option norelax
.include "sw/finish.inc"
.section .text
.global _start
_start:
    li a0,0
    .rept 128
    c.addi a0,1
    .endr
    sd a0,512(zero)
    SIM_EXIT
