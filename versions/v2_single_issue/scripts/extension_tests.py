"""M/A/C, Zicsr and Zifencei execution tests, plus mathematical and byte-level gold values."""
import argparse
from pathlib import Path
import random
from native_test_support import NativeSuite,words

MASK=(1<<64)-1


def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--cross",default="riscv64-elf-"); args=parser.parse_args()
    suite=NativeSuite(args.cross)
    rng=random.Random(20261102)
    body=["lui t6,9"]; expected=[]
    operations="mul mulh mulhsu mulhu div divu rem remu mulw divw divuw remw remuw".split()
    pairs=[(0,0),(1,0),(MASK,0),(MASK-6,3),(7,MASK-2),(1<<63,MASK),(1<<63,1),
           (0x80000000,MASK),(0x7fffffff,0x80000000),(MASK,MASK),(0x123456789abcdef0,0xfedcba9876543210)]
    def sx(v,width):
        return int.from_bytes((v% (1<<width)).to_bytes(width//8,"little"),"little",signed=True)
    for op in operations:
        for a,b in pairs+[(rng.getrandbits(64),rng.getrandbits(64)) for _ in range(8)]:
            width=32 if op.endswith("w") else 64; mask=(1<<width)-1
            ua=a&mask; ub=b&mask; sa=sx(a,width); sb=sx(b,width)
            if op.startswith("mul"):
                value=(sa*sb)>>64 if op=="mulh" else (sa*ub)>>64 if op=="mulhsu" else (ua*ub)>>64 if op=="mulhu" else ua*ub
            else:
                unsigned=op in ("divu","remu","divuw","remuw")
                left,right=(ua,ub) if unsigned else (sa,sb)
                if right==0: quotient=mask; remainder=left
                else:
                    magnitude,unused=divmod(abs(left),abs(right))
                    quotient=-magnitude if (left<0)!=(right<0) else magnitude
                    remainder=left-quotient*right
                value=remainder if op.startswith("rem") else quotient
            if width==32: value=sx(value,32)
            expected.append(value&MASK)
            body += [f"li t0,0x{a:x}",f"li t1,0x{b:x}",f"{op} t2,t0,t1","sd t2,0(t6)","addi t6,t6,8"]
    body += ["SIM_EXIT"]
    suite.compile("native_muldiv","\n".join(body))
    assert Path("build/native_muldiv.bin").stat().st_size<0x9000
    for _,ram in suite.run("native_muldiv"):
        assert words(ram,0x9000,len(expected))==expected

    body=["lui t0,3","lui t6,4"]; atomic_expected=[]
    amo_ops="swap add xor and or min max minu maxu".split()
    for width in (32,64):
        size=width//8; mask=(1<<width)-1; suffix="w" if width==32 else "d"
        for op in amo_ops:
            for old,rhs in [(0,MASK),(MASK,1),(1<<(width-1),7),(0x55aa000080000001,0x87654321)]:
                a=old&mask; b=rhs&mask
                values={"swap":b,"add":a+b,"xor":a^b,"and":a&b,"or":a|b,
                        "min":a if sx(a,width)<sx(b,width) else b,"max":a if sx(a,width)>sx(b,width) else b,
                        "minu":min(a,b),"maxu":max(a,b)}
                new=(old&~mask)|(values[op]&mask)
                atomic_expected += [sx(a,width)&MASK,new&MASK]
                body += [f"li t1,0x{old:x}","sd t1,0(t0)",f"li t2,0x{rhs:x}",f"amo{op}.{suffix}.aqrl t3,t2,(t0)",
                         "sd t3,0(t6)","ld t4,0(t0)","sd t4,8(t6)","addi t6,t6,16"]
        body += ["li t1,7","sd t1,0(t0)",f"lr.{suffix}.aq t2,(t0)","li t1,9",f"sc.{suffix}.rl t3,t1,(t0)",
                 f"sc.{suffix} t4,t1,(t0)","sd t2,0(t6)","sd t3,8(t6)","sd t4,16(t6)","ld t5,0(t0)","sd t5,24(t6)","addi t6,t6,32",
                 f"lr.{suffix} t2,(t0)","sd zero,8(t0)",f"sc.{suffix} t3,t1,(t0)","sd t3,0(t6)","addi t6,t6,8"]
        atomic_expected += [7,0,1,9,1]
    body += ["SIM_EXIT"]
    suite.compile("native_atomics","\n".join(body))
    assert Path("build/native_atomics.bin").stat().st_size<0x3000
    for _,ram in suite.run("native_atomics"):
        assert words(ram,0x4000,len(atomic_expected))==atomic_expected

    suite.compile("native_csrs","""
        li t0,0x55
        csrrw t1,mscratch,t0
        sd t1,512(zero)
        li t3,10
        csrrs t2,mscratch,t3
        sd t2,520(zero)
        li t5,15
        csrrc t4,mscratch,t5
        sd t4,528(zero)
        csrrwi t1,mscratch,3
        sd t1,536(zero)
        csrrsi t2,mscratch,4
        sd t2,544(zero)
        csrrci t3,mscratch,1
        sd t3,552(zero)
        csrr t4,mscratch
        sd t4,560(zero)
        csrr zero,misa
        csrr t1,mhartid
        fence.i
        SIM_EXIT
    """)
    for _,ram in suite.run("native_csrs"):
        assert words(ram,512,7)==[0,0x55,0x5f,0x50,3,7,6]

    suite.compile("native_counter","""
        csrr t0,mcycle
        csrr t1,minstret
        sd t0,512(zero)
        sd t1,520(zero)
        csrwi mcountinhibit,5
        li t0,123
        csrw mcycle,t0
        li t0,45
        csrw minstret,t0
        csrr t1,mcycle
        sd t1,528(zero)
        csrr t1,minstret
        sd t1,536(zero)
        csrwi mcountinhibit,0
        rdtime t2
        sd t2,544(zero)
        SIM_EXIT
    """)
    for _,ram in suite.run("native_counter"):
        assert words(ram,528,2)==[123,45]

    # Trap handler advances over fixed-width faulting instructions and returns to software.
    handler="""
        .org 0x800
    handler:
        csrr t0,mcause
        csrr t1,mscratch
        addi t1,t1,1
        csrw mscratch,t1
        csrr t0,mepc
        addi t0,t0,4
        csrw mepc,t0
        mret
    """
    suite.compile("native_traps","""
        la t0,handler
        csrw mtvec,t0
        .word 0
        ecall
        ebreak
        li ra,0
        csrrs t0,mhartid,ra
        li t0,0x10000
        sc.d t1,zero,(t0)
        csrr t0,mscratch
        sd t0,512(zero)
        SIM_EXIT
    """,handler)
    suite.run("native_traps",signature=5,causes=[2,11,3,2,7])

    suite.compile("native_compressed","""
        li sp,0x7000
        .option rvc
        c.nop
        .option norvc
        addi a0,zero,21
        .option rvc
        c.addi4spn s0,sp,64
        c.li s1,-3
        c.addi s1,1
        c.lui a1,1
        c.addi16sp sp,-32
        c.sdsp s1,0(sp)
        c.ldsp a1,0(sp)
        c.swsp s1,8(sp)
        c.lwsp a2,8(sp)
        c.sw s1,0(s0)
        c.lw a2,0(s0)
        c.sd s1,8(s0)
        c.ld a1,8(s0)
        c.addiw s1,1
        c.slli s1,33
        c.srli s1,32
        c.srai s1,1
        c.andi s1,-1
        c.sub s1,a1
        c.xor s1,a1
        c.or s1,a1
        c.and s1,a1
        c.addw s1,a1
        c.subw s1,a1
        c.mv t0,s1
        c.add t0,a1
        c.li s1,0
        c.beqz s1,1f
        .2byte 0
    1:  c.li s1,2
    2:  c.addi s1,-1
        c.bnez s1,2b
        c.j 3f
        .2byte 0
    3:  c.slli a0,1
        la t0,function
        c.jalr t0
        c.addi a0,-1
        sd a0,512(zero)
        SIM_EXIT
    function:
        c.addi a0,1
        c.jr ra
    """)
    for records,_ in suite.run("native_compressed",signature=42):
        commits=[r for r in records if r["kind"]=="commit"]
        assert any(r["bytes"]==2 for r in commits)
        assert any(r["bytes"]==4 and r["pc"]%4==2 for r in commits)
    for name,half,cause in [("c_break",0x9002,3),("c_reserved",0,2),("c_lwsp_zero",0x4002,2),("c_jr_zero",0x8002,2),("c_addiw_zero",0x2001,2)]:
        suite.compile(name,f"la t0,handler\ncsrw mtvec,t0\n.2byte 0x{half:04x}\nSIM_EXIT",handler.replace("addi t0,t0,4","addi t0,t0,2"))
        suite.run(name,causes=[cause])
    suite.compile("compressed_offsets","""
        li sp,0x7000
        li a1,0x80000001
        .option rvc
        c.addi16sp sp,-512
        c.addi16sp sp,496
        c.addi4spn a0,sp,1020
        sd a0,512(zero)
        c.addi4spn s0,sp,512
        c.sw a1,124(s0)
        c.lw a2,124(s0)
        sd a2,520(zero)
        c.sd a1,248(s0)
        c.ld a2,248(s0)
        sd a2,528(zero)
        c.swsp a1,252(sp)
        c.lwsp a2,252(sp)
        sd a2,536(zero)
        c.sdsp a1,504(sp)
        c.ldsp a2,504(sp)
        sd a2,544(zero)
        c.lui s1,0xfffe0
        sd s1,552(zero)
        c.addiw s1,-32
        sd s1,560(zero)
        c.slli zero,1
        SIM_EXIT
    """)
    for _,ram in suite.run("compressed_offsets"):
        assert words(ram,512,7)==[0x73ec,0xffffffff80000001,0x80000001,0xffffffff80000001,0x80000001,(-0x20000)&MASK,(-0x20020)&MASK]
    suite.compile("native_fence_i","""
        li t0,0x3000
        li t1,0x02a00513
        sw t1,0(t0)
        li t1,0x00008067
        sw t1,4(t0)
        fence.i
        jalr ra,0(t0)
        sd a0,512(zero)
        SIM_EXIT
    """)
    suite.run("native_fence_i",signature=42)
    suite.compile("reservation_snoop","""
        li t0,0x3000
        li t1,7
        sd t1,0(t0)
        lr.d t2,(t0)
        li t3,600
    1:  rdtime t4
        bltu t4,t3,1b
        sc.d t5,t1,(t0)
        sd t5,512(zero)
        SIM_EXIT
    """)
    suite.run("reservation_snoop",signature=1,events=[(500,1<<63),(501,0)])
    suite.compile("native_mmio_time","li t0,0x200bff8\nld t1,0(t0)\nsd t1,512(zero)\nSIM_EXIT")
    for records,ram in suite.run("native_mmio_time"):
        accepted=next(r for r in records if r["kind"]=="mmio_read")
        assert words(ram,512,1)==[accepted["cycle"]]
    suite.compile("csr_warl","""
        li t0,-1
        csrw sstatus,t0
        csrr t1,sstatus
        srli t1,t1,32
        andi t1,t1,3
        sd t1,512(zero)
        li t0,0x1000
        csrw mstatus,t0
        csrr t1,mstatus
        srli t1,t1,11
        andi t1,t1,3
        sd t1,520(zero)
        li t0,0x8ffff00000000006
        csrw satp,t0
        csrr t1,satp
        sd t1,528(zero)
        li t0,0x9000000000000007
        csrw satp,t0
        csrr t1,satp
        sd t1,536(zero)
        li t0,0x222
        csrw mideleg,t0
        csrw mip,t0
        csrw sip,zero
        csrr t1,mip
        sd t1,544(zero)
        SIM_EXIT
    """)
    for _,ram in suite.run("csr_warl"):
        assert words(ram,512,5)==[2,0,(8<<60)|6,(8<<60)|6,0x220]
    suite.compile("csr_seip_not_latched","""
        li ra,0
        csrrs t0,mip,ra
        li t3,1001
    1:  rdtime t4
        bltu t4,t3,1b
        csrr t1,mip
        sd t1,512(zero)
        SIM_EXIT
    """)
    suite.run("csr_seip_not_latched",signature=0,events=[(1,1<<9),(1000,0)])
    for name,signature in [("full_demo",949),("full_demo_o0",949),("machine_demo",3)]:
        suite.run(name,signature=signature,causes=[2,11,3] if name=="machine_demo" else [])
    print(f"EXTENSION PASS: {suite.runs} native runs, {suite.commits} commits, {suite.traps} software-handled traps; {len(expected)} M vectors and {len(atomic_expected)} atomic gold values")


if __name__=="__main__": main()
