"""Check architectural signatures and latency invariants; save reproducible CSV."""
import argparse
import csv
import json
from pathlib import Path
import subprocess
from reference import verify_files

parser = argparse.ArgumentParser()
parser.add_argument("--test", action="store_true")
parser.add_argument("--cross", default="riscv64-elf-")
args = parser.parse_args()
run_count = 0


def run(name, latency, gap=0, fault=0, expected=None):
    global run_count
    trace = f"build/{name}-l{latency}-g{gap}.trace.jsonl"
    proc = subprocess.run(["build/obj_dir/Vrv64_core", f"build/{name}.bin",
                           str(latency), "-", str(gap), trace], capture_output=True, text=True)
    assert proc.returncode == (2 if fault else 0), (name, proc.stdout, proc.stderr)
    stats = json.loads(proc.stdout)
    assert stats["fault"] == fault, (name, stats)
    if expected is not None:
        assert stats["result"] == expected, (name, stats)
    checked = verify_files(f"build/{name}.bin", trace)
    assert checked == stats["instret"]
    run_count += 1
    return stats


rows = []
for name, result, retired in [("sum", 2080, 325), ("dependency", 128, 260),
                              ("pointer_chase", 2016, 325), ("load_add_store", 14, 30)]:
    baseline = None
    for latency in [1, 5, 20]:
        stats = run(name, latency, expected=result)
        assert stats["instret"] == retired, (name, stats)
        assert stats["fetch_wait"] == retired * (latency - 1)
        assert stats["data_wait"] == (stats["requests"] - retired) * (latency - 1)
        if baseline is None:
            baseline = stats
        assert stats["cycles"] == baseline["cycles"] + stats["requests"] * (latency - 1)
        rows.append(dict(program=name, latency=latency, **stats))
    if args.test:
        for latency, gap in [(1, 3), (5, 7)]:
            stats = run(name, latency, gap, expected=result)
            assert stats["instret"] == retired

if args.test:
    # Assembly is encoded by the real toolchain, independently of the RTL decoder.
    cases = {
        "arithmetic": ("""
            addi zero, zero, 123
            addi t0, zero, -7
            addi t1, zero, 12
            add t2, t0, t1
            sub t2, t2, t0
            sd t2, 512(zero)
            ebreak
        """, 0, 12),
        "load_store": ("""
            lui t0, 1
            addi t1, zero, -9
            sd t1, 0(t0)
            ld t2, 0(t0)
            ld zero, 0(t0)
            addi t2, t2, 10
            sd t2, 512(zero)
            ebreak
        """, 0, 1),
        "branches": ("""
            addi t0, zero, -1
            addi t1, zero, 1
            blt t0, t1, 1f
            .word 0
        1:  bge t1, t0, 2f
            .word 0
        2:  bltu t1, t0, 3f
            .word 0
        3:  bgeu t0, t1, 4f
            .word 0
        4:  beq zero, zero, 5f
            .word 0
        5:  bne zero, zero, 6f
            jal t2, 7f
        6:  .word 0
        7:  sd t2, 512(zero)
            ebreak
        """, 0, 56),
        "lui_sign": ("lui t0, 0xfffff\nsd t0, 512(zero)\nebreak", 0, (1 << 64) - 4096),
        "illegal": (".word 0xffffffff", 1, 0),
        "illegal_addi": (".word 0x00101093", 1, 0),  # SLLI is outside subset
        "misaligned_load": ("ld t0, 1(zero)", 2, 0),
        "misaligned_store": ("sd zero, 1(zero)", 2, 0),
        "misaligned_jump": (".word 0x0020006f", 2, 0),
        "access_fault": ("lui t0, 16\nld t1, 0(t0)", 3, 0),
        "fetch_fault": (".word 0x0001006f", 3, 0),  # JAL x0, 0x10000
        "store_fault": ("lui t0, 16\nsd zero, 0(t0)", 3, 0),
        "wraparound": ("addi t0, zero, -1\naddi t0, t0, 1\nsd t0, 512(zero)\nebreak", 0, 0),
        "bad_branch": (".word 0x00002063", 1, 0),
        "bad_load": (".word 0x00002283", 1, 0),
    }
    for name, (body, fault, expected) in cases.items():
        source = Path(f"build/{name}.S")
        source.write_text(".option norvc\n.section .text\n.global _start\n_start:\n" + body + "\n")
        subprocess.run([args.cross + "gcc", "-march=rv64i", "-mabi=lp64", "-nostdlib",
                        "-Wl,-Ttext=0,-e,_start,--no-relax", "-o", f"build/{name}.elf", str(source)], check=True)
        subprocess.run([args.cross + "objcopy", "-O", "binary", "-j", ".text",
                        f"build/{name}.elf", f"build/{name}.bin"], check=True)
        for latency, gap in [(1, 0), (5, 3)]:
            run(name, latency, gap, fault, expected)
    print(f"PASS: {run_count} runs; every commit, halt status and full RAM checked against reference")

destination = Path("build/results.csv")
with destination.open("w", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
print(destination.read_text(), end="")
