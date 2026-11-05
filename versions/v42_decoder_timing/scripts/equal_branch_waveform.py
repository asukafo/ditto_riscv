"""Export same-register branch predictions from the two registered fetch slots."""
import argparse
import csv
import sys

from waveforms import read_vcd, value_at


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("vcd")
    args = parser.parse_args()
    core = read_vcd(args.vcd)
    front = read_vcd(args.vcd, ["TOP", "rv64_core", "frontend"])
    writer = csv.writer(sys.stdout)
    writer.writerow(["cycle", "slot", "pc", "instruction", "next_pc", "dynamic"])
    mask = (1 << 64) - 1
    cycle = 0
    for t, clk in core["clk"]:
        if not clk or value_at(core["reset"], t, True):
            continue
        cycle += 1
        if not value_at(front["complete"], t, True):
            continue
        post = lambda name: value_at(core[name], t)
        entries = [(0, post("raw_fe_pc"), post("raw_fe_insn"),
                    post("raw_fe_predicted_next"), post("raw_fe_predicted_dynamic"))]
        if post("raw_fe_second_valid"):
            packet = post("raw_fe_second_packet")
            entries.append((1, packet >> 269, (packet >> 45) & 0xffffffff,
                            (packet >> 205) & mask, (packet >> 6) & 1))
        for slot, pc, insn, nxt, dynamic in entries:
            if insn & 127 == 0x63 and (insn >> 15) & 31 == (insn >> 20) & 31:
                writer.writerow([cycle, slot, hex(pc), hex(insn), hex(nxt), dynamic])


if __name__ == "__main__":
    main()
