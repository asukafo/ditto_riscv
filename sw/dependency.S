.option norvc
.section .text
.global _start
_start:
    addi t0, zero, 0
    addi t1, zero, 64
loop:
    addi t0, t0, 1
    addi t0, t0, 1
    addi t1, t1, -1
    bne t1, zero, loop
    sd t0, 512(zero)
    ebreak
