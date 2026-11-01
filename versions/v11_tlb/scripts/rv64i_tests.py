"""RV64I width, word, control, terminal-trap and compiler integration tests."""
import argparse
import json
from pathlib import Path
import random
import subprocess

from reference import Fault, Reference, verify_files

MASK = (1 << 64) - 1
REQUIRED = set("""lui auipc jal jalr beq bne blt bge bltu bgeu
lb lh lw ld lbu lhu lwu sb sh sw sd
addi slti sltiu xori ori andi slli srli srai
add sub sll slt sltu xor srl sra or and
addiw slliw srliw sraiw addw subw sllw srlw sraw fence ecall ebreak""".split())


class Suite:
    def __init__(self, cross):
        self.cross, self.runs, self.covered = cross, 0, set()

    def compile(self, name, body, data=""):
        source = f'.option norvc\n.include "sw/finish.inc"\n.section .text\n.global _start\n_start:\n{body}\n{data}\n'
        Path(f"build/{name}.S").write_text(source)
        subprocess.run([self.cross+"gcc", "-march=rv64i", "-mabi=lp64", "-nostdlib",
                        "-Wl,-Ttext=0,-e,_start,--no-relax", "-o", f"build/{name}.elf", f"build/{name}.S"], check=True)
        subprocess.run([self.cross+"objcopy", "-O", "binary", "-j", ".text", f"build/{name}.elf", f"build/{name}.bin"], check=True)

    def coverage(self, image):
        model = Reference(image)
        while not model.stopped:
            try:
                _, name = model.step()
                self.covered.add(name)
            except Fault as fault:
                if fault.code in (4, 5):
                    self.covered.add("ecall" if fault.code == 4 else "ebreak")
                break

    def run(self, name, fault=0, signature=None, trap=None, timings=None, status=0):
        image = Path(f"build/{name}.bin").read_bytes()
        self.coverage(image)
        outputs = []
        for latency, gap in timings or [(1, 0), (5, 3), (20, 7)]:
            trace = f"build/{name}-l{latency}-g{gap}.trace.jsonl"
            proc = subprocess.run(["build/obj_dir/Vrv64_core", f"build/{name}.bin", str(latency), "-", str(gap), trace], capture_output=True, text=True)
            assert proc.returncode == (2 if fault else 3 if status else 0), (name, proc.stdout, proc.stderr)
            count = verify_files(f"build/{name}.bin", trace)
            records = [json.loads(line) for line in Path(trace).read_text().splitlines()]
            ram = Path(trace+".ram").read_bytes()
            assert records[-1]["fault"] == fault
            assert records[-1]["exit_status"] == status
            if signature is not None:
                assert int.from_bytes(ram[512:520], "little") == signature, name
            if trap is not None:
                actual = tuple(records[-1][key] for key in ("trap_cause", "trap_pc", "trap_value"))
                assert actual == trap, (name, actual, trap)
            assert count == len(records)-1
            outputs.append((records, ram))
            self.runs += 1
        return outputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cross", default="riscv64-elf-")
    args = parser.parse_args()
    suite = Suite(args.cross)
    # Also include the actually simulated 19-operation ALU vector image.
    verify_files("build/alu_vectors.bin", "build/alu_vectors-l1-g0.trace.jsonl")
    suite.coverage(Path("build/alu_vectors.bin").read_bytes())

    # Verify every load width and signedness against independent byte decoding.
    memory = bytearray([0xaa]*64)
    stores = [("sb", 1, 0x123456789abcdef0, 1), ("sh", 2, 0x8001, 2),
              ("sw", 4, 0x80000001, 4), ("sd", 8, 0x8877665544332211, 8)]
    body = ["lui t0,1", "lui t6,2", "sb zero,0(t0)"]
    memory[0] = 0
    for op, offset, value, size in stores:
        body += [f"li t1,0x{value:x}", f"{op} t1,{offset}(t0)"]
        memory[offset:offset+size] = (value % (1 << (8*size))).to_bytes(size, "little")
    loads = []
    for op, size, signed in [("lb",1,True),("lbu",1,False),("lh",2,True),("lhu",2,False),
                              ("lw",4,True),("lwu",4,False),("ld",8,True)]:
        for offset in range(0,16,size):
            body += [f"{op} t2,{offset}(t0)", "sd t2,0(t6)", "addi t6,t6,8"]
            loads.append(int.from_bytes(memory[offset:offset+size], "little", signed=signed)&MASK)
    body += ["lbu zero,1(t0)", "SIM_EXIT"]
    suite.compile("memory_widths", "\n".join(body), ".org 0x1000\n.fill 64,1,0xaa")
    for records, ram in suite.run("memory_widths"):
        assert ram[0x1000:0x1040] == memory  # includes all untouched adjacent bytes
        for i, value in enumerate(loads):
            assert int.from_bytes(ram[0x2000+8*i:0x2008+8*i], "little") == value
        zero_load = [r for r in records[:-1] if r["mem_valid"] and not r["mem_write"] and not r["rd_wen"]]
        assert len(zero_load) == 1 and zero_load[0]["mem_addr"] == 0x1001

    # The very last byte/halfword/word are valid now that requests have a size.
    suite.compile("ram_boundary", """
        li t0,0xffff
        li t1,-128
        sb t1,0(t0)
        lbu t2,0(t0)
        sd t2,512(zero)
        li t0,0xfffe
        sh t1,0(t0)
        lh t2,0(t0)
        li t0,0xfffc
        sw t1,0(t0)
        lw t2,0(t0)
        SIM_EXIT
    """)
    suite.run("ram_boundary", signature=128)
    suite.compile("fetch_last_word", "li t0,0xfffc\nli t1,0x00100073\nsw t1,0(t0)\njalr zero,0(t0)")
    suite.run("fetch_last_word", fault=5, trap=(3,0xfffc,0))

    # All nine W instructions, with a mathematical 32-bit oracle and alias writes.
    rng = random.Random(20261101)
    word_ops = "addw subw sllw srlw sraw addiw slliw srliw sraiw".split()
    word_values = [0,1,0x7fffffff,0x80000000,0xffffffff,0x8000000000000000,0x1234567880000001,MASK]
    vectors = []
    for op in word_ops:
        immediate = op in ("addiw","slliw","srliw","sraiw")
        amounts = [-2048,-1,0,1,2047] if op == "addiw" else [0,1,15,31] if immediate else [0,1,31,32,33,63,64,MASK]
        pairs = [(a,b) for a in word_values for b in amounts]
        pairs += [(rng.getrandbits(64),rng.randrange(-2048,2048) if op=="addiw" else rng.randrange(32) if immediate else rng.getrandbits(64)) for _ in range(8)]
        for a,b in pairs:
            for rd in ([7,5,6,0] if (a,b)==pairs[0] else [7]):
                low = a % (1<<32)
                shift = b % 32
                if op in ("addw","addiw"): value=low+b
                elif op=="subw": value=low-b
                elif op in ("sllw","slliw"): value=low*(2**shift)
                elif op in ("srlw","srliw"): value=low//(2**shift)
                else: value=int.from_bytes(low.to_bytes(4,"little"),"little",signed=True)//(2**shift)
                low_result=value%(1<<32)
                value=int.from_bytes(low_result.to_bytes(4,"little"),"little",signed=True)&MASK
                vectors.append((op,a,b,rd,value if rd else 0))
    body=["lui x30,9"]
    for op,a,b,rd,_ in vectors:
        immediate=op in ("addiw","slliw","srliw","sraiw")
        body += [f"li x5,0x{a:x}", f"li x6,0x{b&MASK:x}",
                 f"{op} x{rd},x5,{b if immediate else 'x6'}", f"sd x{rd},0(x30)", "addi x30,x30,8"]
    body += ["SIM_EXIT"]
    suite.compile("word_vectors","\n".join(body))
    assert Path("build/word_vectors.bin").stat().st_size < 0x9000
    for _,ram in suite.run("word_vectors"):
        for i,v in enumerate(vectors):
            actual=int.from_bytes(ram[0x9000+8*i:0x9008+8*i],"little")
            assert actual==v[4], (v,actual)

    suite.compile("auipc", "addi zero,zero,0\nauipc t0,1\nsd t0,512(zero)\nauipc t1,0xfffff\nsd t1,520(zero)\nSIM_EXIT")
    for _,ram in suite.run("auipc",signature=4100):
        assert int.from_bytes(ram[520:528],"little")==((12-4096)&MASK)
    suite.compile("jalr_alias", "addi t0,zero,17\njalr t0,0(t0)\n.word 0\n.word 0\nsd t0,512(zero)\nSIM_EXIT")
    suite.run("jalr_alias", signature=8)
    suite.compile("fences", "addi t0,zero,7\nfence iorw,iorw\n.word 0xfff2828f\n.word 0x8330000f\nsd t0,512(zero)\nSIM_EXIT")
    suite.run("fences",signature=7)
    # Each branch executes once taken and once not taken, with manual next-PC checks.
    for op, taken, untaken in [("beq",(1,1),(1,2)),("bne",(1,2),(1,1)),
                              ("blt",(-1,1),(1,-1)),("bge",(1,-1),(-1,1)),
                              ("bltu",(1,-1),(-1,1)),("bgeu",(-1,1),(1,-1))]:
        for take,(a,b) in [(True,taken),(False,untaken)]:
            name=f"branch_{op}_{int(take)}"
            suite.compile(name,f"addi t0,zero,{a}\naddi t1,zero,{b}\n{op} t0,t1,1f\naddi t2,zero,9\n1: SIM_EXIT")
            for records,_ in suite.run(name):
                assert records[2]["pc"]==8 and records[2]["next_pc"]==(16 if take else 12)

    # Exact trap metadata and absence of successful retirement on the faulting instruction.
    traps={
        "trap_ecall":("addi t0,zero,1\necall",4,(11,4,0)),
        "trap_ebreak":("addi t0,zero,1\nebreak",5,(3,4,0)),
        "trap_lh":("lh t0,1(zero)",2,(4,0,1)),
        "trap_lw":("lw t0,2(zero)",2,(4,0,2)),
        "trap_sh":("sh zero,1(zero)",2,(6,0,1)),
        "trap_sw":("sw zero,2(zero)",2,(6,0,2)),
        "trap_lb_x0":("lui t0,16\nlb zero,0(t0)",3,(5,4,65536)),
        "trap_sb":("lui t0,16\nsb zero,0(t0)",3,(7,4,65536)),
        "trap_jalr":("addi t0,zero,3\njalr t1,0(t0)",2,(0,4,2)),
        "trap_branch":("addi t0,zero,0\n.word 0x00028163",2,(0,4,6)),
    }
    for name,(body,fault,trap) in traps.items():
        suite.compile(name,body+"\nsd t0,512(zero)")
        for records,_ in suite.run(name,fault=fault,signature=0,trap=trap):
            assert records[-1]["instret"] == trap[1]//4
    for name,word in {"slliw_reserved":0x0202929b,"srliw_reserved":0x0202d29b,
                      "sraiw_reserved":0x4202d29b,"op32_badfunct":0x0062f3bb,
                      "jalr_badfunct":0x000012e7,"store_badwidth":0x00504023,
                      "csr_unsupported":0x300022f3,"fence_i_unsupported":0x0000100f}.items():
        suite.compile(name,f".word 0x{word:08x}")
        suite.run(name,fault=1,trap=(2,0,word))
    suite.compile("branch_misaligned_not_taken", "addi t0,zero,1\n.word 0x00028163\nSIM_EXIT")
    suite.run("branch_misaligned_not_taken")
    suite.compile("mailbox_narrow", "li t0,0xfff0\nsb zero,0(t0)\naddi t1,zero,42\nsd t1,512(zero)\nSIM_EXIT")
    suite.run("mailbox_narrow",signature=42)
    suite.compile("mailbox_failure", "li t0,0xfff0\naddi t1,zero,1\nsd t1,0(t0)")
    suite.run("mailbox_failure",status=1)
    for name in ("c_demo","c_demo_o0"):
        suite.run(name,signature=1488)
    missing=REQUIRED-suite.covered
    assert not missing, f"unexecuted RV64I instructions: {sorted(missing)}"
    Path("build/rv64i-coverage.json").write_text(json.dumps(dict(required=sorted(REQUIRED),executed=sorted(suite.covered),runs=suite.runs,word_vectors=len(vectors),load_vectors=len(loads)),indent=2)+"\n")
    print(f"RV64I PASS: {suite.runs} runs, all {len(REQUIRED)} base instructions executed, {len(vectors)} W vectors, {len(loads)} load-width vectors; C -O0/-O2 result=1488")


if __name__ == "__main__":
    main()
