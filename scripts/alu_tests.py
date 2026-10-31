"""Assembler-encoded ALU vectors with a separate mathematical result oracle.

Compare full commit traces to reference.py AND memory results to these vectors.
No third-party Python dependencies. Inputs and seed are deterministic.
"""
import argparse
import json
from pathlib import Path
import random
import subprocess

from reference import verify_files

MASK = (1 << 64) - 1
SIGN = 1 << 63
REGISTER_OPS = "add sub and or xor sll srl sra slt sltu".split()
IMMEDIATE_OPS = "addi andi ori xori slti sltiu slli srli srai".split()


def expected(op, a, b):
    signed_a = (a ^ SIGN) - SIGN
    unsigned_b = b & MASK
    signed_b = (unsigned_b ^ SIGN) - SIGN
    amount = b if op.endswith("i") else b % 64
    if op in ("add", "addi"):
        result = a + b
    elif op == "sub":
        result = a - b
    elif op in ("and", "andi"):
        result = a & unsigned_b
    elif op in ("or", "ori"):
        result = a | unsigned_b
    elif op in ("xor", "xori"):
        result = a ^ unsigned_b
    elif op in ("sll", "slli"):
        result = a * (2 ** amount)
    elif op in ("srl", "srli"):
        result = a // (2 ** amount)
    elif op in ("sra", "srai"):
        result = signed_a // (2 ** amount)
    elif op in ("slt", "slti"):
        result = int(signed_a < signed_b)
    elif op in ("sltu", "sltiu"):
        result = int(a < unsigned_b)
    else:
        raise ValueError(op)
    return result & MASK


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cross", default="riscv64-elf-")
    args = parser.parse_args()
    rng = random.Random(20261031)
    vectors = []

    def add(op, a, b, rd=7, rs1=5, rs2=6):
        a &= MASK
        b = b & MASK if op in REGISTER_OPS else b
        left = 0 if rs1 == 0 else a
        right = (0 if rs2 == 0 else a if rs2 == 5 else b) if op in REGISTER_OPS else b
        vectors.append(dict(op=op, a=a, b=b, rd=rd, rs1=rs1, rs2=rs2,
                            expected=expected(op, left, right) if rd else 0))

    edge_pairs = [(0, 0), (1, 1), (MASK, 0), (MASK, 1), (SIGN, MASK), (SIGN, 0),
                  (SIGN-1, SIGN), (SIGN, 1), (MASK, MASK), (0, MASK),
                  (0x0123456789abcdef, 0xfedcba9876543210)]
    edge_pairs += [(SIGN | 3, n) for n in (31, 32, 63, 64, 65, 127, 128)]
    for op in REGISTER_OPS:
        for a, b in edge_pairs + [(rng.getrandbits(64), rng.getrandbits(64)) for _ in range(12)]:
            add(op, a, b)
    edge_inputs = [0, 1, MASK, SIGN, SIGN-1, MASK-7, 0x0123456789abcdef, 0xaaaaaaaaaaaaaaaa]
    for op in IMMEDIATE_OPS:
        immediates = [0, 1, 31, 32, 63] if op in ("slli", "srli", "srai") else [-2048, -1, 0, 1, 63, 2047]
        for a in edge_inputs:
            for b in immediates:
                add(op, a, b)
        for _ in range(8):
            add(op, rng.getrandbits(64), rng.randrange(64) if op in ("slli", "srli", "srai") else rng.randrange(-2048, 2048))
    # Write/read aliases, discarded x0 results, and x0 source operands.
    for op in REGISTER_OPS + IMMEDIATE_OPS:
        operand = 63 if op in ("slli", "srli", "srai") else 1
        for destination in (0, 5, 6):
            add(op, SIGN | 9, operand, rd=destination)
        add(op, SIGN | 9, operand, rs1=0)
        if op in REGISTER_OPS:
            add(op, SIGN | 9, operand, rs2=0)
            add(op, SIGN | 9, operand, rs2=5)

    # Hard-coded semantic examples guard mistakes in the mathematical oracle itself.
    assert expected("srai", MASK-7, 1) == 0xfffffffffffffffc
    assert expected("srli", MASK-7, 1) == 0x7ffffffffffffffc
    assert expected("sll", 1, 64) == 1
    assert expected("sltiu", SIGN, -1) == 1
    assert expected("slt", SIGN, 0) == 1 and expected("sltu", SIGN, 0) == 0

    body = [".option norvc", ".section .text", ".global _start", "_start:", "lui x30, 8", "lui x31, 12"]
    for v in vectors:
        operand = f"x{v['rs2']}" if v["op"] in REGISTER_OPS else str(v["b"])
        body += ["ld x5, 0(x30)", "ld x6, 8(x30)",
                 f"{v['op']} x{v['rd']}, x{v['rs1']}, {operand}",
                 f"sd x{v['rd']}, 0(x31)", "addi x30, x30, 16", "addi x31, x31, 8"]
    body += ["ebreak", ".org 0x8000"]
    body += [f".dword 0x{v['a']:016x}, 0x{v['b'] & MASK:016x}" for v in vectors]
    assert (2 + 6 * len(vectors) + 1) * 4 < 0x8000
    assert 0x8000 + 16 * len(vectors) <= 0xc000
    assert 0xc000 + 8 * len(vectors) <= 65536
    Path("build/alu_vectors.S").write_text("\n".join(body) + "\n")
    Path("build/alu_vectors.json").write_text(json.dumps(vectors, indent=2) + "\n")
    subprocess.run([args.cross+"gcc", "-march=rv64i", "-mabi=lp64", "-nostdlib",
                    "-Wl,-Ttext=0,-e,_start,--no-relax", "-o", "build/alu_vectors.elf", "build/alu_vectors.S"], check=True)
    subprocess.run([args.cross+"objcopy", "-O", "binary", "-j", ".text", "build/alu_vectors.elf", "build/alu_vectors.bin"], check=True)
    total_commits = 0
    for latency, gap in [(1, 0), (1, 3), (5, 0), (5, 7), (20, 3)]:
        trace = f"build/alu_vectors-l{latency}-g{gap}.trace.jsonl"
        proc = subprocess.run(["build/obj_dir/Vrv64_core", "build/alu_vectors.bin", str(latency), "-", str(gap), trace],
                              capture_output=True, text=True)
        assert proc.returncode == 0, (proc.stdout, proc.stderr)
        count = verify_files("build/alu_vectors.bin", trace)
        assert count == 3 + 6 * len(vectors)
        total_commits += count
        memory = Path(trace + ".ram").read_bytes()
        records = [json.loads(line) for line in Path(trace).read_text().splitlines()]
        for i, v in enumerate(vectors):
            address = 0xc000 + 8*i
            actual = int.from_bytes(memory[address:address+8], "little")
            assert actual == v["expected"], (i, v, hex(actual), latency, gap)
            event = records[4 + 6*i]
            assert event["rd_wen"] == int(v["rd"] != 0)
            assert event["rd"] == v["rd"]
            assert event["wdata"] == v["expected"]
    print(f"ALU PASS: {len(vectors)} vectors across 19 operations × 5 timing configurations; {total_commits} commits checked")


if __name__ == "__main__":
    main()
