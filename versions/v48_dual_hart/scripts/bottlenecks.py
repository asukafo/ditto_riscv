"""Classify each active pre-edge cycle and each blocked second decode from VCD."""
import csv
from collections import Counter
from pathlib import Path
import sys

from waveforms import read_vcd, value_at


from dual_tests import pair_integer


def audit(path):
    core = read_vcd(path)
    fetch = read_vcd(path, ["TOP", "rv64_core", "frontend"])
    totals = Counter()
    for t, clk in core["clk"]:
        def pre(name):
            return value_at(core[name], t, True)

        def front(name):
            return value_at(fetch[name], t, True)

        if not clk or pre("reset") or pre("halted"):
            continue
        totals["cycles"] += 1
        totals["control_misses"] += pre("control_miss_event")
        if pre("issue_fire"):
            if pre("pair_fire"):
                reason = "dual_issue"
            elif not pre("second_valid"):
                reason = "one_no_second"
            elif not pair_integer(pre("fe_insn")) or not pair_integer(pre("p2_insn")):
                reason = "one_opcode"
            elif pre("pair_raw") or pre("pair_waw"):
                reason = "one_dependency"
            else:
                reason = "one_other"
        elif pre("frontend_starved"):
            reason = "frontend_empty"
        elif pre("ex_finish") and not pre("fe_valid") and not pre("fetch_redirect"):
            reason = "frontend_empty_x_finish"
        elif pre("state") in (2, 3) and not pre("ex_finish"):
            reason = "data_wait"
        elif pre("state") == 4 and not pre("ex_finish"):
            reason = "muldiv_wait"
        else:
            reason = "other_no_issue"
        totals[reason] += 1
        if "second_control" in fetch and front("complete") and front("contiguous"):
            if not front("candidate_illegal") and front("tail_count") >= front("second_bytes"):
                if front("second_control") and not front("emit_second"):
                    totals["second_control_deferred"] += 1
    return totals


if __name__ == "__main__":
    rows = [(Path(p).stem, audit(p)) for p in sys.argv[1:]]
    keys = sorted(set().union(*(r.keys() for _, r in rows)))
    writer = csv.writer(sys.stdout)
    writer.writerow(["run", *keys])
    for name, totals in rows:
        writer.writerow([name, *(totals[k] for k in keys)])
