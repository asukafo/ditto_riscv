"""Render actual Verilator VCD transitions using only Python's standard library.

make diagrams regenerates the VCDs, annotated SVGs, and pre-edge sample CSVs.
PNG export, if desired: rsvg-convert -o output.png input.svg
"""
from pathlib import Path
from html import escape
import csv

STATES = {0: "FQ", 1: "FW", 2: "EX", 3: "DQ", 4: "DW", 5: "STOP"}


def read_vcd(path, scope=None):
    scope=scope or ["TOP", "rv64_core"]
    names, traces, scopes = {}, {}, []
    stamp = 0
    for line in Path(path).read_text().splitlines():
        words = line.strip().split()
        if not words:
            continue
        if words[0] == "$scope":
            scopes.append(words[2])
        elif words[0] == "$upscope":
            scopes.pop()
        elif words[0] == "$var" and scopes == scope:
            names[words[4]] = words[3]
            traces.setdefault(words[3], [])
        elif line.startswith("#"):
            stamp = int(line[1:])
        elif line[0] in "01bxz":
            if line[0] == "b":
                value, code = words[0][1:], words[1]
            else:
                value, code = line[0], line[1:]
            if code in traces:
                value = int(value, 2) if not any(c in value for c in "xz") else None
                if not traces[code] or traces[code][-1][1] != value:
                    traces[code].append((stamp, value))
    result={name: traces[code] for name, code in names.items()}
    if "regs[28]" not in result and "debug_t3" in result:
        result["regs[28]"]=result["debug_t3"]
    return result


def value_at(trace, time, before=False):
    value = None
    for stamp, new in trace:
        if stamp > time or (before and stamp == time):
            break
        value = new
    return value


def draw(source, destination, title, latency, gap):
    traces = read_vcd(source)
    rising = [t for t, v in traces["clk"] if v == 1 and value_at(traces["reset"], t) == 0]
    # First LD at PC=0x0c: include its fetch through its successful data response.
    first = next(t for t in rising if value_at(traces["pc"], t, True) == 12
                 and value_at(traces["state"], t, True) == 0)
    done = next(t for t in rising if t > first and value_at(traces["commit_valid"], t) == 1
                and value_at(traces["commit_pc"], t) == 12)
    # Include the subsequent ADD, demonstrating that it only starts after LD commits.
    finish = next(t for t in rising if t > done and value_at(traces["commit_valid"], t) == 1
                  and value_at(traces["commit_pc"], t) == 16)
    edges = [t for t in rising if first <= t <= finish]
    period = rising[1] - rising[0]
    rows = [("clk", "bit"), ("state", "state"), ("pc", "hex"),
            ("req_valid", "bit"), ("req_ready", "bit"), ("req_addr", "hex"),
            ("rsp_valid", "bit"), ("rsp_ready", "bit"), ("rsp_rdata", "low32"),
            ("regs[28]", "hex"), ("commit_valid", "bit"), ("commit_pc", "hex"),
            ("data_wait", "int")]
    left, top, step, cell = 155, 102, 34, 72
    width = left + cell * (len(edges) + 1) + 25
    height = top + step * len(rows) + 74
    lo, hi = first - period / 2, finish + period / 2
    def x(time):
        return left + (time - lo) / period * cell
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
           '<rect width="100%" height="100%" fill="#fff"/>',
           '<style>text{font-family:Arial,sans-serif;fill:#172d42;font-size:15px}.signal{font-family:Menlo,monospace;font-size:14px}.small{font-size:12px}</style>',
           f'<text x="20" y="28" style="font-size:21px">{escape(title)}</text>',
           f'<text x="20" y="51">Actual VCD | LATENCY={latency}, GAP={gap} | LD t3,0(t0) at PC=0x0c, then ADD at 0x10</text>']
    for i, t in enumerate(edges):
        xx = x(t)
        svg += [f'<line x1="{xx}" y1="85" x2="{xx}" y2="{top + step * len(rows)}" stroke="#d7dfe7" stroke-dasharray="3 4"/>',
                f'<text x="{xx}" y="78" text-anchor="middle">C{i}</text>']
    for row, (name, kind) in enumerate(rows):
        y = top + step * row
        label = "t3 (x28)" if name == "regs[28]" else "rsp_low32" if kind == "low32" else name
        color = "#b45309" if name.startswith("req_") else "#087f75" if name.startswith("rsp_") else "#245cc5"
        svg.append(f'<text x="12" y="{y+15}" class="signal">{escape(label)}</text>')
        points = [(lo, value_at(traces[name], lo))] + [(t, v) for t, v in traces[name] if lo < t < hi] + [(hi, value_at(traces[name], hi))]
        if kind == "bit":
            path = []
            for i, (t, v) in enumerate(points):
                yy = y + (2 if v == 1 else 23)
                path.append(f'{"M" if i == 0 else "H"} {x(t):.2f}' + (f' {yy}' if i == 0 else f' V {yy}'))
            svg.append(f'<path d="{" ".join(path)}" fill="none" stroke="{color}" stroke-width="1.8"/>')
        else:
            for (start, v), (end, _) in zip(points, points[1:]):
                if start == end:
                    continue
                xx, xe = x(start), x(end)
                svg.append(f'<path d="M {xx+3} {y+2} H {xe-3} L {xe} {y+12} L {xe-3} {y+23} H {xx+3} L {xx} {y+12} Z" fill="#f5f8fc" stroke="#a7b6c8"/>')
                text = "?" if v is None else STATES.get(v, "?") if kind == "state" else str(v) if kind == "int" else f"0x{(v & 0xffffffff) if kind == 'low32' else v:x}"
                if xe-xx > len(text)*8+6:
                    svg.append(f'<text x="{(xx+xe)/2}" y="{y+17}" text-anchor="middle" class="signal">{text}</text>')
    footer = top + step * len(rows)
    svg += [f'<text x="20" y="{footer+25}" class="small">FQ=fetch request | FW=fetch response | EX=execute | DQ=data request | DW=data response</text>',
            f'<text x="20" y="{footer+47}" class="small">Ck marks a rising edge. Handshakes use values BEFORE that edge; registers/state update AFTER it.</text>',
            f'<text x="20" y="{footer+65}" class="small">Time is relative cycles, not a physical clock-frequency claim. Bus values matter only during valid handshakes.</text>', '</svg>']
    Path(destination).write_text("\n".join(svg) + "\n")
    # A machine-readable audit of the figure: edge inputs before, state/output after.
    csv_path = Path(destination).with_suffix(".csv")
    samples = []
    for i, t in enumerate(edges):
        pre = {name: value_at(traces[name], t, True) for name, _ in rows}
        post = {name: value_at(traces[name], t) for name in ["state", "pc", "regs[28]", "commit_valid", "commit_pc", "data_wait"]}
        samples.append(dict(edge=i, **{"pre_"+k: v for k, v in pre.items()},
                            **{"post_"+k: v for k, v in post.items()}))
    with csv_path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(samples[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(samples)
    requests = [i for i, s in enumerate(samples) if s["pre_req_valid"] and s["pre_req_ready"]]
    responses = [i for i, s in enumerate(samples) if s["pre_rsp_valid"] and s["pre_rsp_ready"]]
    commits = [i for i, s in enumerate(samples) if s["post_commit_valid"]]
    assert len(requests) == len(responses) == 3
    assert all(b-a == latency for a, b in zip(requests, responses))
    assert value_at(traces["regs[28]"], done) == 1
    assert value_at(traces["pc"], done) == 16
    print(f"{destination}: request edges={requests}, response edges={responses}, commit edges={commits}")


if __name__ == "__main__":
    Path("docs/waveforms").mkdir(parents=True, exist_ok=True)
    for name, latency, gap, title in [
        ("load-l1", 1, 0, "Load instruction: minimum response latency"),
        ("load-l5", 5, 0, "Load instruction: waiting for memory"),
        ("load-gap3", 1, 3, "Load instruction: request backpressure"),
    ]:
        draw(f"build/{name}.vcd", f"docs/waveforms/{name}.svg", title, latency, gap)
