"""Sample a demand arriving on the D-cache's successful tail response edge."""
import argparse
import csv
import sys

from waveforms import read_vcd, value_at


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wave")
    args = parser.parse_args()
    core = read_vcd(args.wave)
    cache = read_vcd(args.wave, ["TOP", "rv64_core", "memory_system", "split", "dcache"])
    fields = (
        "u_addr", "u_valid", "u_ready", "tail_pending", "d_rsp_valid", "d_rsp_error",
        "returned_half", "background_accept", "u_rsp_valid", "u_rsp_ready",
    )
    rows = [{f: value_at(cache[f], t, True) for f in fields}
            for t, clk in core["clk"] if clk and not value_at(core["reset"], t, True)]
    anchor = next(i for i, r in enumerate(rows) if r["background_accept"] and r["returned_half"])
    writer = csv.writer(sys.stdout)
    writer.writerow(["cycle", *fields])
    for i in range(max(0, anchor - 3), min(len(rows), anchor + 4)):
        writer.writerow([i + 1, *(hex(rows[i][f]) if f == "u_addr" else rows[i][f] for f in fields)])


if __name__ == "__main__":
    main()
