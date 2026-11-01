.option norvc
.option norelax
.include "sw/finish.inc"
.section .text
.global _start
_start:

    li a0,0
    la t0,handler
    csrw mtvec,t0
    li t0,0x8000000000000006
    csrw satp,t0
    li t0,0x800
    csrw mstatus,t0
    li t0,0x40000000
    csrw mepc,t0
    mret


    .org 0x800
handler:
    csrr t0,mepc
    sd t0,768(zero)
    csrr t0,mtval
    sd t0,776(zero)
    sd a0,512(zero)
    SIM_EXIT

.org 0x1000

        li t0,0x40001000
        li t1,64
        li a0,0
    1:  ld t2,0(t0)
        add a0,a0,t2
        addi t1,t1,-1
        bnez t1,1b
        ecall

.org 0x2000
.dword 7
.org 0x3000
.dword 99

    .org 0x6000
    .dword 0,0x1c01
    .org 0x7000
    .dword 0x2001
    .org 0x8000

.dword 0x44b,0x8c7
