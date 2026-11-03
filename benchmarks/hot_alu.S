.option norvc
.option norelax
.include "sw/finish.inc"
.section .text
.global _start
_start:
 li s0,128
 li a0,0
 li a1,0
 li a2,0
 li a3,0
 li a4,0
 li a5,0
 li a6,0
 li a7,0
1:
 addi a0,a0,1
 addi a1,a1,1
 addi a2,a2,1
 addi a3,a3,1
 addi a4,a4,1
 addi a5,a5,1
 addi a6,a6,1
 addi a7,a7,1
 addi s0,s0,-1
 bnez s0,1b
 add a0,a0,a1
 add a0,a0,a2
 add a0,a0,a3
 add a0,a0,a4
 add a0,a0,a5
 add a0,a0,a6
 add a0,a0,a7
 sd a0,512(zero)
 SIM_EXIT
