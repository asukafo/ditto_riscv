"""Extract rising-edge samples around a taken prediction in the second slot."""
import argparse
import csv
import sys

from waveforms import read_vcd, value_at


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("wave")
    args = parser.parse_args()
    core = read_vcd(args.wave)
    fetch = read_vcd(args.wave, ["TOP", "rv64_core", "frontend"])
    edges = [t for t, clk in core["clk"] if clk and not value_at(core["reset"], t, True)]

    def pre(signals, name, time):
        return value_at(signals[name], time, True)

    anchor = next(i for i, t in enumerate(edges)
                  if pre(core, "wide_decode_pair_event", t)
                  and pre(fetch, "second_conditional", t)
                  and pre(fetch, "second_next", t) != pre(fetch, "second_sequential", t))
    writer = csv.writer(sys.stdout)
    writer.writerow(["edge", "decoded_first_pc", "second_pc", "second_next", "pair_decode",
                     "f_valid", "f_ready", "f_addr", "issue_fire", "issue_pc", "redirect"])
    for i in range(max(0, anchor - 2), min(len(edges), anchor + 7)):
        t = edges[i]
        writer.writerow([i + 1, hex(pre(fetch, "next_pc", t)),
                         hex(pre(fetch, "candidate_next", t)), hex(pre(fetch, "second_next", t)),
                         pre(core, "wide_decode_pair_event", t),
                         pre(core, "f_valid", t), pre(core, "f_ready", t), hex(pre(core, "f_addr", t)),
                         pre(core, "issue_fire", t), hex(pre(core, "fe_pc", t)), pre(core, "fetch_redirect", t)])


if __name__ == "__main__":
    main()
