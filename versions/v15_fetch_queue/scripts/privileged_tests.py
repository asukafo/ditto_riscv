"""M/S/U trap return, interrupts, Sv39/Svade and cross-page fetch integration."""
import argparse
from native_test_support import NativeSuite,words

HIGH=1<<63
DATA=0x40001000
HANDLER="""
    .org 0x800
handler:
    csrr a1,mcause
    sd a1,768(zero)
    csrr a2,mtval
    sd a2,776(zero)
    csrr a3,mepc
    sd a3,784(zero)
    sd a0,512(zero)
    li t0,0x20000
    csrc mstatus,t0
    li t0,0x1800
    csrs mstatus,t0
    la t0,finish
    csrw mepc,t0
    mret
finish:
    SIM_EXIT
"""


def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--cross",default="riscv64-elf-"); args=parser.parse_args()
    suite=NativeSuite(args.cross)

    def paging(name,code_flags=0x4b,data_flags=0xc7,status=0,priv=1,root=6,entry=0x40000000,
               program=None,expected_cause=9,signature=0x1234,extra_leaf=0,handler=HANDLER,data_ppn=2):
        boot=f"""
            la t0,handler
            csrw mtvec,t0
            li a0,0
            li t0,{(8<<60)|root:#x}
            csrw satp,t0
            li t0,{status|(priv<<11):#x}
            csrw mstatus,t0
            li t0,{entry:#x}
            csrw mepc,t0
            mret
        """
        code=program or f"li t0,{DATA:#x}\nld a0,0(t0)\necall"
        data=f"""{handler}
            .org 0x1000
        supervisor:
            {code}
            .org 0x2000
            .dword 0x1234
            .org 0x3000
            .dword 0x5678
            .org 0x6000
            .dword 0,0x1c01
            .org 0x7000
            .dword 0x2001
            .org 0x8000
            .dword {0x400|code_flags:#x},{(data_ppn<<10)|data_flags:#x},{extra_leaf:#x}
        """
        suite.compile(name,boot,data)
        return suite.run(name,signature=signature,causes=expected_cause if isinstance(expected_cause,list) else [expected_cause])

    paging("sv39_supervisor")
    paging("sv39_mapped_exit",data_ppn=15,program="li t0,0x40001ff0\nsd zero,0(t0)",expected_cause=[],signature=0)
    paging("sv39_user",code_flags=0x5b,data_flags=0xd7,priv=0,expected_cause=8)
    paging("sv39_user_code_denied",priv=0,data_flags=0xd7,expected_cause=12,signature=0)
    paging("sv39_user_data_denied",priv=0,code_flags=0x5b,expected_cause=13,signature=0)
    paging("sv39_sum_denied",data_flags=0xd7,expected_cause=13,signature=0)
    paging("sv39_sum_allowed",data_flags=0xd7,status=1<<18)
    paging("sv39_sum_never_executes_user",code_flags=0x5b,data_flags=0xd7,status=1<<18,expected_cause=12,signature=0)
    paging("sv39_mxr_denied",data_flags=0xc9,expected_cause=13,signature=0)
    paging("sv39_mxr_allowed",data_flags=0xc9,status=1<<19)
    paging("sv39_invalid_rw",data_flags=0x45,expected_cause=13,signature=0)
    paging("sv39_reserved_pte",code_flags=(1<<63)|0x4b,expected_cause=12,signature=0)
    paging("sv39_no_accessed",data_flags=0x87,expected_cause=13,signature=0)
    paging("sv39_no_dirty",data_flags=0x47,program=f"li t0,{DATA:#x}\nsd zero,0(t0)\necall",expected_cause=15,signature=0)
    paging("sv39_failed_sc_permissions",data_flags=0x43,program=f"li t0,{DATA:#x}\nsc.d a0,zero,(t0)\necall",expected_cause=15,signature=0)
    paging("sv39_walk_bus_error",root=16,expected_cause=1,signature=0)
    paging("sv39_noncanonical_fetch",entry=1<<39,expected_cause=12,signature=0)
    paging("sv39_noncanonical_load",program=f"li t0,{1<<39:#x}\nld a0,0(t0)\necall",expected_cause=13,signature=0)
    # A software handler sets A/D, retries exactly the same instruction, then handles ECALL.
    repair="""
        .org 0x800
handler:
        sd t0,896(zero)
        sd t1,904(zero)
        csrr t0,mcause
        li t1,13
        beq t0,t1,repair
        li t1,15
        beq t0,t1,repair
        sd a0,512(zero)
        li t0,0x1800
        csrs mstatus,t0
        la t0,finish
        csrw mepc,t0
        mret
repair:
        li t0,0x8008
        li t1,0xc0
        amoor.d zero,t1,(t0)
        ld t0,896(zero)
        ld t1,904(zero)
        mret
finish:
        SIM_EXIT
    """
    paging("svade_repair_accessed",data_flags=0x87,handler=repair,expected_cause=[13,9])
    paging("svade_repair_dirty",data_flags=0x47,handler=repair,
           program=f"li t0,{DATA:#x}\nli a0,77\nsd a0,0(t0)\necall",expected_cause=[15,9],signature=77)
    paging("sv39_sfence_remap",extra_leaf=0x20c7,
           program=f"li t0,0x40002000\nli t1,0xcc7\nsd t1,8(t0)\nsfence.vma\nli t0,{DATA:#x}\nld a0,0(t0)\necall",signature=0x5678)
    for records,ram in paging("sv39_atomic_alias",extra_leaf=0x8c7,
           program=f"li t0,{DATA:#x}\nlr.d a0,(t0)\nli t1,0x40002000\nli t2,0x777\nsc.d a1,t2,(t1)\nadd a0,a0,a1\necall"):
        assert words(ram,0x2000,1)==[0x777]
        sc=[r for r in records if r["kind"]=="commit" and r["mem_atomic"] and r["mem_amo"]==3]
        assert len(sc)==1 and sc[0]["wdata"]==0

    # MPRV affects data accesses only. Instruction fetch remains physical in M mode.
    mprv_body=f"""
        la t0,handler
        csrw mtvec,t0
        li t0,{(8<<60)|6:#x}
        csrw satp,t0
        li t0,{(1<<17)|(1<<11):#x}
        csrw mstatus,t0
        li t0,{DATA:#x}
        ld a0,0(t0)
        ecall
    """
    data=HANDLER+"\n.org 0x2000\n.dword 0x1234\n.org 0x6000\n.dword 0,0x1c01\n.org 0x7000\n.dword 0x2001\n.org 0x8000\n.dword 0,0x8c7"
    suite.compile("sv39_mprv",mprv_body,data)
    suite.run("sv39_mprv",signature=0x1234,causes=[11])

    # Superpages: leaf at level 2 (1 GiB) or level 1 (2 MiB), with aligned PPN=0.
    for level in (2,1):
        for misaligned in (False,True):
            boot=f"la t0,handler\ncsrw mtvec,t0\nli a0,0\nli t0,{(8<<60)|6:#x}\ncsrw satp,t0\nli t0,0x800\ncsrw mstatus,t0\nli t0,0x40001000\ncsrw mepc,t0\nmret"
            leaf=(0x400 if misaligned else 0)|0xcf
            root=leaf if level==2 else 0x1c01
            data=HANDLER+f"\n.org 0x1000\nli t0,0x40002000\nld a0,0(t0)\necall\n.org 0x2000\n.dword 0x1234\n.org 0x6000\n.dword 0,{root:#x}"
            if level==1: data+=f"\n.org 0x7000\n.dword {leaf:#x}"
            name=f"superpage_{level}_{int(misaligned)}"; suite.compile(name,boot,data)
            suite.run(name,signature=0 if misaligned else 0x1234,causes=[12 if misaligned else 9])

    # A 32-bit instruction starts at the last halfword of one page; the next is non-contiguous.
    for mapped in (True,False):
        boot=f"la t0,handler\ncsrw mtvec,t0\nli a0,0\nli t0,{(8<<60)|6:#x}\ncsrw satp,t0\nli t0,0x800\ncsrw mstatus,t0\nli t0,0x40000ffe\ncsrw mepc,t0\nmret"
        data=HANDLER+f"\n.org 0x1ffe\n.2byte 0x0513\n.org 0x3000\n.2byte 0x02a0\n.4byte 0x73\n.org 0x6000\n.dword 0,0x1c01\n.org 0x7000\n.dword 0x2001\n.org 0x8000\n.dword 0x44b,{0xc4b if mapped else 0:#x}"
        name=f"cross_page_{int(mapped)}"; suite.compile(name,boot,data)
        for records,_ in suite.run(name,signature=42 if mapped else 0,causes=[9 if mapped else 12]):
            trap=next(r for r in records if r["kind"]=="trap")
            assert trap["pc"]==(0x40001002 if mapped else 0x40000ffe)
            assert trap["value"]==(0 if mapped else 0x40001000)

    # M->S->U; U ECALL delegates to S, then an illegal M CSR in U traps to M.
    suite.compile("privilege_delegation","""
        la t0,handler
        csrw mtvec,t0
        la t0,s_handler
        csrw stvec,t0
        li t0,0x100
        csrw medeleg,t0
        li t0,0x800
        csrw mstatus,t0
        la t0,supervisor
        csrw mepc,t0
        mret
    """,HANDLER+"""
        .org 0x900
s_handler:
        csrr t0,scause
        sd t0,792(zero)
        csrr t0,sepc
        addi t0,t0,4
        csrw sepc,t0
        sret
        .org 0x1000
supervisor:
        la t0,user
        csrw sepc,t0
        sret
user:
        li a0,42
        ecall
        csrr t0,mstatus
    """)
    for records,ram in suite.run("privilege_delegation",signature=42,causes=[8,2]):
        assert words(ram,792,1)==[8]
        assert {r["privilege"] for r in records if r["kind"]=="commit"}=={0,1,3}

    for name,status,instruction in [("tvm_satp",1<<20,"csrr a0,satp"),("tvm_sfence",1<<20,"sfence.vma"),
                                    ("tsr_sret",1<<22,"sret"),("tw_wfi",1<<21,"wfi")]:
        suite.compile(name,f"la t0,handler\ncsrw mtvec,t0\nli a0,0\nli t0,{status|0x800:#x}\ncsrw mstatus,t0\nla t0,supervisor\ncsrw mepc,t0\nmret",HANDLER+f"\n.org 0x1000\nsupervisor:\n{instruction}")
        suite.run(name,signature=0,causes=[2])

    for priv,mcounter,scounter,allowed in [(0,0,0,False),(0,7,0,False),(0,7,7,True),(1,7,0,True)]:
        name=f"counter_permissions_{priv}_{mcounter}_{scounter}"
        body=f"la t0,handler\ncsrw mtvec,t0\nli a0,0\nli t0,{mcounter}\ncsrw mcounteren,t0\nli t0,{scounter}\ncsrw scounteren,t0\nli t0,{priv<<11}\ncsrw mstatus,t0\nla t0,lower\ncsrw mepc,t0\nmret"
        suite.compile(name,body,HANDLER+"\n.org 0x1000\nlower:\nrdcycle a0\nrdtime a1\nrdinstret a2\necall")
        for _,ram in suite.run(name,causes=[(8 if priv==0 else 9) if allowed else 2]):
            value=words(ram,512,1)[0]
            assert value>0 if allowed else value==0

    # Timer/software interrupts use the simulated CLINT; external IRQs use timestamped input files.
    for source,number in [("timer",7),("software",3),("external",11),("priority",11)]:
        pending="li t0,0x2004000\nrdtime t1\naddi t1,t1,120\nsd t1,0(t0)" if source=="timer" else "li t0,0x2000000\nli t1,1\nsw t1,0(t0)" if source=="software" else ""
        clear="li t0,0x2004000\nli t1,-1\nsd t1,0(t0)" if source=="timer" else "li t0,0x2000000\nsw zero,0(t0)" if source=="software" else "li t0,0x888\ncsrc mie,t0"
        mask=0x888 if source=="priority" else 1<<number
        body=f"la t0,vectors\nori t0,t0,1\ncsrw mtvec,t0\nli t0,{mask:#x}\ncsrw mie,t0\ncsrsi mstatus,8\n{pending}\n1: csrr t0,mscratch\nwfi\nbeq t0,zero,1b\nsd t0,512(zero)\nSIM_EXIT"
        data=f"\n.org 0x800\nvectors:\n.rept 12\njal zero,irq_handler\n.endr\nirq_handler:\nsd t0,896(zero)\nsd t1,904(zero)\ncsrr t0,mcause\nsd t0,768(zero)\n{clear}\ncsrwi mscratch,1\nld t0,896(zero)\nld t1,904(zero)\nmret"
        name=f"irq_{source}"; suite.compile(name,body,data)
        events=[(500,mask)] if source in ("external","priority") else None
        for records,ram in suite.run(name,signature=1,causes=[HIGH|number],events=events):
            trap=next(r for r in records if r["kind"]=="trap")
            assert trap["target"]==0x800+4*number
            assert words(ram,768,1)==[HIGH|number]

    suite.compile("irq_supervisor","la t0,handler\ncsrw mtvec,t0\nla t0,s_irq\ncsrw stvec,t0\nli t0,2\ncsrw mideleg,t0\ncsrw mie,t0\nli t0,0x800\ncsrw mstatus,t0\nla t0,supervisor\ncsrw mepc,t0\nmret",HANDLER+"""
        .org 0x900
s_irq:
        csrci sip,2
        csrwi sscratch,1
        sret
        .org 0x1000
supervisor:
        csrsi sstatus,2
        csrsi sip,2
        csrr a0,sscratch
        ecall
    """)
    suite.run("irq_supervisor",signature=1,causes=[HIGH|1,9])
    print(f"PRIVILEGED PASS: {suite.runs} native runs, {suite.commits} commits, {suite.traps} software-handled traps; Sv39/Svade, M/S/U, vectored and delegated interrupts")


if __name__=="__main__": main()
