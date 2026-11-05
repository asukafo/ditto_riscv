# Simulation EEI exit: a committed SD to 0xfff0, zero means success.
# Clobbers t4/x29. ECALL and EBREAK are architectural traps, never normal exit.
.macro SIM_EXIT
    lui t4, 16
    addi t4, t4, -16
    sd zero, 0(t4)
.endm
