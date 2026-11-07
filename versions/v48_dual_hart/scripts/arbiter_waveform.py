"""Sample the first contended arbitration and its response from a native VCD."""
import argparse
import csv
import sys

from waveforms import read_vcd, value_at


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wave")
    args = parser.parse_args()
    core = read_vcd(args.wave)
    scope = ["TOP", "rv64_core", "memory_system", "split", "physical_arbiter"]
    arbiter = read_vcd(args.wave, scope)
    grants = read_vcd(args.wave, [*scope, "parallel_grant"])
    fields = ("state", "turn", "owner", "c_valid", "c_ready",
              "u_valid", "u_ready", "c_rsp_valid", "u_rsp_ready")
    rows = []
    for t, clk in core["clk"]:
        if clk and not value_at(core["reset"], t, True):
            row = {name: value_at(arbiter[name], t, True) for name in fields}
            row["grant"] = value_at(grants["grant"], t, True)
            rows.append(row)
    anchor = next(i for i, r in enumerate(rows)
                  if r["state"] == 0 and r["c_valid"] & (r["c_valid"] - 1))
    end = next(i for i in range(anchor + 1, len(rows))
               if rows[i]["c_rsp_valid"] and rows[i]["u_rsp_ready"])
    writer = csv.writer(sys.stdout)
    writer.writerow(["cycle", *fields, "grant"])
    for i in range(max(0, anchor - 1), min(len(rows), end + 2)):
        r = rows[i]
        writer.writerow([i + 1, *(r[name] for name in fields), r["grant"]])


if __name__ == "__main__":
    main()
