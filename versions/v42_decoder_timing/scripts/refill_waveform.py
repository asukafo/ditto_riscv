"""Sample demand, refill and return at the first two cache turnover edges."""
import argparse
import csv
import sys

from waveforms import read_vcd, value_at


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wave")
    parser.add_argument("cache", choices=("icache", "dcache"))
    args = parser.parse_args()
    core = read_vcd(args.wave)
    cache = read_vcd(args.wave, ["TOP", "rv64_core", "memory_system", "split", args.cache])
    fields = (
        "u_valid", "u_ready", "u_addr", "direct_refill", "d_valid", "d_ready", "d_addr",
        "d_rsp_valid", "forward_critical", "u_rsp_valid", "u_rsp_ready", "response_available",
    )
    rows = []
    for t, clk in core["clk"]:
        if not clk or value_at(core["reset"], t, True):
            continue
        rows.append({name: value_at(cache[name], t, True) for name in fields})
    launch = next(i for i, row in enumerate(rows) if row["direct_refill"] and row["d_ready"])
    returned = next(i for i in range(launch + 1, len(rows)) if rows[i]["forward_critical"])
    writer = csv.writer(sys.stdout)
    writer.writerow(["cycle", *fields])
    for i in range(max(0, launch - 1), min(len(rows), returned + 4)):
        writer.writerow([i + 1, *(hex(rows[i][f]) if f.endswith("_addr") else rows[i][f] for f in fields)])


if __name__ == "__main__":
    main()
