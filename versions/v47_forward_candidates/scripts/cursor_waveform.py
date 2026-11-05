"""Extract the first useful cursor skip and neighboring fetch handshakes."""
import argparse
import csv
import sys

from waveforms import read_vcd, value_at


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wave")
    args = parser.parse_args()
    core = read_vcd(args.wave)
    window = read_vcd(args.wave, ["TOP", "rv64_core", "request_window", "window"])
    edges = [t for t, clk in core["clk"] if clk and not value_at(core["reset"], t, True)]
    ports = ("f_addr", "f_valid", "f_ready", "f_rsp_valid", "issue_fire")
    internals = ("spec_pc", "alloc_pc", "advance", "allocate", "found", "retarget")
    anchor = next(i for i, t in enumerate(edges)
                  if value_at(window["advance"], t, True)
                  and value_at(window["spec_pc"], t, True) != value_at(window["alloc_pc"], t, True))
    writer = csv.writer(sys.stdout)
    writer.writerow(["cycle", *ports, *internals])
    for i in range(max(0, anchor - 2), min(len(edges), anchor + 7)):
        t = edges[i]
        row = [i + 1]
        for signals, fields in ((core, ports), (window, internals)):
            for name in fields:
                value = value_at(signals[name], t, True)
                row.append(hex(value) if name.endswith(("_pc", "_addr")) else value)
        writer.writerow(row)


if __name__ == "__main__":
    main()
