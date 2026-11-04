"""Map a version in an isolated directory using its existing timing constraints."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parent.parent
REGISTER_MARKER = "REGISTER TO REGISTER SETUP"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_logged(command, directory, filename, env=None):
    with (directory / filename).open("w") as log:
        subprocess.run(command, cwd=directory, env=env, stdout=log,
                       stderr=subprocess.STDOUT, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", choices=sorted(
        p.parent.name for p in (ROOT / "versions").glob("*/version.json")))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--clock", type=float, default=10.0, help="Clock constraint in ns")
    parser.add_argument("--lib", type=Path, default=Path.home() /
                        ".local/opt/opensta/share/lib/NangateOpenCellLibrary_typical.lib")
    args = parser.parse_args()
    if not math.isfinite(args.clock) or args.clock <= 0:
        parser.error("--clock must be a positive finite value")
    if not args.lib.is_file():
        parser.error(f"Liberty file not found: {args.lib}")

    version = ROOT / "versions" / args.version
    rtl = sorted((version / "rtl").glob("*.sv"))
    constraints = version / "scripts/abc.constr"
    timing = version / "scripts/timing.tcl"
    for path in (constraints, timing):
        if not path.is_file():
            parser.error(f"Version lacks required constraints: {path}")
    if not rtl:
        parser.error("Version has no SystemVerilog sources")
    tcl = timing.read_text().rstrip().splitlines()
    if not tcl or tcl[-1].strip() != "exit":
        parser.error("Version timing script must end with exit")
    tcl[-1:] = [
        f'puts "{REGISTER_MARKER}"',
        "report_checks -from [all_registers -output_pins] -to [all_registers -data_pins]"
        " -path_delay max -group_path_count 1 -digits 4",
        "exit",
    ]

    output = args.output.resolve()
    try:
        output.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        parser.error(f"Output directory already exists: {output}")
    (output / "build").mkdir()
    lib = json.dumps(str(args.lib.resolve()))
    sources = " ".join(json.dumps(str(path)) for path in rtl)
    flow = (
        f"read_verilog -sv {sources}; synth -flatten -top rv64_core; "
        f"dfflibmap -liberty {lib}; abc -liberty {lib} -constr {json.dumps(str(constraints))}; "
        f"read_liberty -lib {lib}; clean; check -assert; stat -liberty {lib}; "
        "write_verilog -noattr -noexpr build/core_mapped.v"
    )
    (output / "mapping.ys").write_text(flow + "\n")
    (output / "timing.tcl").write_text("\n".join(tcl) + "\n")
    run_logged(["yosys", "-Q", "-T", "-s", "mapping.ys"], output, "mapping.log")
    env = dict(os.environ, LIB=str(args.lib.resolve()), CLOCK_NS=str(args.clock))
    run_logged(["sta", "-exit", "timing.tcl"], output, "timing.log", env)

    report = (output / "timing.log").read_text()
    mapping = (output / "mapping.log").read_text()
    general, _, registers = report.partition(REGISTER_MARKER)
    pattern = r"(-?[0-9.]+)\s+slack \("
    full_match = re.search(pattern, general)
    reg_match = re.search(pattern, registers)
    if not full_match or not reg_match:
        raise RuntimeError(f"Missing setup path in {output / 'timing.log'}")
    slack = float(full_match[1])
    period = round(args.clock - float(reg_match[1]), 4)
    area = float(re.search(r"Chip area for module.*?:\s+([0-9.]+)", mapping)[1])
    summary = dict(
        version=args.version, mapping="flatten", clock_constraint_ns=args.clock,
        reg_to_reg_period_ns=period, full_setup_ns=round(args.clock - slack, 4),
        mapped_area=area, liberty_sha256=digest(args.lib),
        abc_constraints_sha256=digest(constraints), timing_tcl_sha256=digest(timing),
        rtl_sha256={p.name: digest(p) for p in rtl},
        mapped_netlist_sha256=digest(output / "build/core_mapped.v"),
        yosys=subprocess.check_output(["yosys", "-V"], text=True).strip(),
        opensta=subprocess.check_output(["sta", "-version"], text=True).strip(),
    )
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"{args.version}: {period} ns, mapped area {area:.3f}; {output}")


if __name__ == "__main__":
    main()
