"""Compare a mapped simulator against the native RTL traces from a public run."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent.parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", choices=sorted(
        p.parent.name for p in (ROOT / "versions").glob("*/version.json")))
    parser.add_argument("run")
    parser.add_argument("mapped_simulator", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.run.replace("-", "").replace("_", "").isalnum():
        parser.error("Invalid public run identifier")
    version = ROOT / "versions" / args.version
    archive = version / "results" / args.run
    build = version / "build"
    manifest = json.loads((archive / "manifest.json").read_text())
    if manifest["version"] != args.version or manifest["run_id"] != args.run:
        parser.error("Archive does not match the requested run")
    simulator = args.mapped_simulator.resolve()
    if not simulator.is_file():
        parser.error(f"Mapped simulator not found: {simulator}")
    out = args.output.resolve()
    try:
        out.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        parser.error(f"Output directory already exists: {out}")

    verified = []
    with (archive / "performance.csv").open() as stream:
        for row in csv.DictReader(stream):
            program, latency, gap = (row[k] for k in ("program", "latency", "gap"))
            image = build / f"{program}.bin"
            if digest(image) != manifest["images"][program]:
                raise ValueError(f"Image differs from the archived run: {image}")
            name = f"{args.run}-{program}-full-l{latency}-g{gap}.trace.jsonl"
            mapped_trace = out / name
            rtl_trace = build / name
            stats = json.loads(subprocess.check_output(
                [simulator, image, latency, "-", gap, mapped_trace], text=True))
            keys = ("cycles", "requests", "control_misses", "instret")
            for key in keys:
                if stats[key] != int(row[key]):
                    raise ValueError(f"{name}: mapped {key}={stats[key]}, RTL {key}={row[key]}")
            for suffix in ("", ".ram"):
                if digest(Path(str(mapped_trace) + suffix)) != digest(Path(str(rtl_trace) + suffix)):
                    raise ValueError(f"{name}{suffix} differs from the RTL run")
            verified.append(dict(program=program, latency=latency, gap=gap,
                                 **{key: stats[key] for key in keys}))
    if not verified:
        raise ValueError("No public cases in the selected archive")
    with (out / "verified.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(verified[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(verified)
    print(f"{len(verified)} mapped runs matched RTL trace bytes and final RAM")


if __name__ == "__main__":
    main()
