"""Measure X dispatch and cache refill turnover independently on the public images."""
import argparse
import csv
import json
from pathlib import Path
import subprocess
import sys

from reference import verify_files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline_csv", type=Path)
    parser.add_argument("images", type=Path)
    args = parser.parse_args()
    modes = ("nodataturn", "launchonly", "refillonly", "full")
    writer = csv.writer(sys.stdout)
    writer.writerow(["program", "latency", "gap", *modes])
    with args.baseline_csv.open() as stream:
        for row in csv.DictReader(stream):
            program, latency, gap = (row[k] for k in ("program", "latency", "gap"))
            image = args.images / f"{program}.bin"
            cycles = []
            for mode in modes:
                trace = Path(f"build/data-ablation-{program}-{latency}-{gap}-{mode}.jsonl")
                output = subprocess.check_output(
                    [f"build/{mode}_obj/Vrv64_core", image, latency, "-", gap, trace],
                    text=True,
                )
                stats = json.loads(output)
                assert verify_files(image, trace) == stats["instret"]
                cycles.append(stats["cycles"])
            assert cycles[0] == int(row["cycles"]), (program, latency, gap)
            writer.writerow([program, latency, gap, *cycles])


if __name__ == "__main__":
    main()
