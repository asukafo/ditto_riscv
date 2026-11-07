.section .text
.globl _start
_start:
    csrr s0, mhartid
    li s1, 0x4000
    li s3, 0xfff8
    li s4, 0x4100
    li s5, 0x4400
    beqz s0, id_ok
    li t0, 1
    bne s0, t0, fail
id_ok:
    # Both harts increment one shared counter. Lost AMO updates fail the test.
    li t0, 64
    li t1, 1
amo_loop:
    amoadd.d.aqrl zero, t1, (s5)
    addi t0, t0, -1
    bnez t0, amo_loop
    addi s2, s1, 8
    bnez s0, hart1

    # The testbench advances the peer's gate after each LR retires.
    lr.d t0, (s2)
    bnez t0, fail
wait_conflict:
    ld t0, 16(s1)
    beqz t0, wait_conflict
    li t1, 99
    sc.d t0, t1, (s2)
    li t2, 1
    bne t0, t2, fail
    ld t0, 8(s1)
    li t2, 7
    bne t0, t2, fail

    lr.d t0, (s2)
    bne t0, t2, fail
wait_unrelated:
    ld t0, 24(s1)
    beqz t0, wait_unrelated
    sc.d t0, t1, (s2)
    bnez t0, fail
    # Keep an old shared line in hart 0's L1D and confirm a hot re-read.
    ld t0, 0(s4)
    bnez t0, fail
    ld t0, 0(s4)
    bnez t0, fail
    li t0, 1
    sd t0, 64(s1)
wait_peer_store:
    ld t0, 72(s1)
    beqz t0, wait_peer_store
    ld t0, 0(s4)
    li t1, 0x5a000000
    bne t0, t1, fail
    ld t0, 8(s4)
    li t1, 42
    bne t0, t1, fail

    # Same L1 set, two L2 lines. Repeated alternation exercises L2 reuse.
    li t2, 0x4200
    li t3, 8
l2_loop:
    ld t0, 8(s4)
    bne t0, t1, fail
    ld t0, 0(t2)
    bnez t0, fail
    addi t3, t3, -1
    bnez t3, l2_loop
    li t0, 1
    sd t0, 32(s1)
    j park

hart1:
    li t0, 1
wait_first_lr:
    ld t1, 0(s3)
    bltu t1, t0, wait_first_lr
    li t1, 7
    # A byte store overlaps the doubleword reserved by the peer.
    sb t1, 0(s2)
    sd t0, 16(s1)
    li t0, 2
wait_second_lr:
    ld t1, 0(s3)
    bltu t1, t0, wait_second_lr
    sd t0, 24(s1)
wait_peer_cache:
    ld t1, 64(s1)
    beqz t1, wait_peer_cache
    ld t1, 0(s4)
    bnez t1, fail
    ld t1, 0(s4)
    bnez t1, fail
    li t1, 0x5a
    sb t1, 3(s4)
    li t1, 42
    sd t1, 8(s4)
    sd t0, 72(s1)
    sd t0, 40(s1)
park:
    j park
fail:
    ebreak
