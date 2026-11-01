.option norvc
.option norelax
.section .text.start,"ax",@progbits
.global _start
_start:
    la sp, __stack_top
    la t0, __bss_start
    la t1, __bss_end
1:
    beq t0, t1, 2f
    sd zero, 0(t0)
    addi t0, t0, 8
    jal zero, 1b
2:
    call main
    sd a0, 512(zero)       # main's result signature, independent of host exit status
    lui t4, 16
    addi t4, t4, -16
    sd zero, 0(t4)
3:
    jal zero, 3b
