"""Count issue edges where removing only the intra-pair RAW guard would enable pairing."""
import csv
from pathlib import Path
import sys

from waveforms import read_vcd, value_at


def measure(path):
    signals = read_vcd(path)
    opportunities = add_producers = 0
    for time, clk in signals["clk"]:
        if not clk:
            continue

        def pre(name):
            return value_at(signals[name], time, True)

        if not (pre("issue_fire") and pre("second_valid") and pre("pair_raw")
                and not pre("pair_waw") and pre("p1_pair_op") and pre("p2_pair_op")):
            continue
        if pre("fe_illegal") or pre("fe_fault") or (pre("second_packet") >> 8) & 3:
            continue
        if not (pre("p2_pc") == pre("fe_predicted_next") == pre("fe_pc") + pre("fe_bytes")
                and pre("p2_next") == pre("p2_pc") + pre("p2_bytes")):
            continue
        opportunities += 1
        insn = pre("fe_insn")
        if (insn >> 12) & 7 == 0 and (insn & 127 == 0x13 or
                                      (insn & 127 == 0x33 and insn >> 25 == 0)):
            add_producers += 1
    return opportunities, add_producers


def main():
    archive, wave_folder = map(Path, sys.argv[1:])
    writer = csv.writer(sys.stdout)
    writer.writerow(["program", "latency", "gap", "cycles", "raw_only", "add_producer"])
    with archive.open() as stream:
        for row in csv.DictReader(stream):
            case = [row[key] for key in ("program", "latency", "gap")]
            wave = wave_folder / ("-".join(case) + ".vcd")
            writer.writerow([*case, row["cycles"], *measure(wave)])


if __name__ == "__main__":
    main()
