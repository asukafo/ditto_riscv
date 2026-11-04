.option norvc
.option norelax
.include "sw/finish.inc"
.section .text
.global _start
_start:
    la t0,handler
    csrw mtvec,t0
    .word 0               # illegal instruction -> handler -> MRET
    ecall                 # cause 11 in M mode
    ebreak                # cause 3; no longer terminates the simulation
    csrr t0,mscratch
    sd t0,512(zero)       # expected: three handled traps
    SIM_EXIT
.org 0x800
handler:
    sd t0,896(zero)
    csrr t0,mscratch
    addi t0,t0,1
    csrw mscratch,t0
    csrr t0,mepc
    addi t0,t0,4          # this example deliberately uses 32-bit instructions only
    csrw mepc,t0
    ld t0,896(zero)
    mret
