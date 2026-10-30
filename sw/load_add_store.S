.option norvc
.section .text
.global _start
_start:
    lui t0, 1                # x5 = 0x1000: input array
    addi t1, zero, 4         # four elements
    addi t2, zero, 10        # add 10 to every element
loop:
    ld t3, 0(t0)
    add t3, t3, t2
    sd t3, 0(t0)             # write the updated value back
    addi t0, t0, 8
    addi t1, t1, -1
    bne t1, zero, loop       # taken three times, then falls through
    ld t3, -8(t0)            # read back last updated element: 14
    sd t3, 512(zero)         # result signature
    ebreak
.org 0x1000
.dword 1, 2, 3, 4
