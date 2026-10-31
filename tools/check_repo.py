"""Check repository layout, local documentation links and immutable experiment archives."""
import csv
import hashlib
import json
import os
from pathlib import Path
import re
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_rows(path):
    with path.open(newline='') as stream:
        return list(csv.DictReader(stream))


def markdown_files():
    for directory, folders, files in os.walk(ROOT):
        folders[:] = [name for name in folders if name not in {'.git', '.local', 'build', '__pycache__'}]
        for name in files:
            if name.endswith('.md'):
                yield Path(directory) / name


def main():
    for duplicate in ('rtl', 'scripts', 'sim', 'sw'):
        require(not (ROOT / duplicate).exists(), f'Root {duplicate}/ duplicates a version directory')

    versions = sorted((ROOT / 'versions').glob('v*/version.json'))
    require(bool(versions), 'No hardware versions found')
    for metadata in versions:
        folder = metadata.parent
        require(json.loads(metadata.read_text())['name'] == folder.name, f'Invalid version name: {metadata}')
        for relative in ('Makefile', 'README.md', 'rtl/rv64_core.sv', 'sim/main.cpp',
                         'sw/finish.inc', 'scripts/reference.py'):
            require((folder / relative).is_file(), f'Missing version file: {folder / relative}')

    frozen = ROOT / 'versions/v1_multicycle'
    manifest = json.loads((frozen / 'frozen-files.json').read_text())
    for relative, expected in manifest['files'].items():
        path = frozen / relative
        require(path.is_file(), f'Missing frozen source: {path}')
        require(hashlib.sha256(path.read_bytes()).hexdigest() == expected, f'Frozen source changed: {path}')

    comparisons = sorted((ROOT / 'results/comparisons').glob('*/comparison.csv'))
    rows_checked = 0
    for comparison in comparisons:
        rows = read_rows(comparison)
        require(bool(rows), f'Empty comparison: {comparison}')
        run_id = comparison.parent.name
        participants = {row['version'] for row in rows}
        for version in participants:
            results = ROOT / 'versions' / version / 'results' / run_id
            require(results.is_dir(), f'Missing single-version results: {results}')
            saved = read_rows(results / 'performance.csv')
            require(saved == [row for row in rows if row['version'] == version],
                    f'Comparison differs from single-version archive: {comparison}, {version}')
            record = json.loads((results / 'manifest.json').read_text())
            require(record['version'] == version and record['run_id'] == run_id,
                    f'Result metadata mismatch: {results}')
        for key in {(row['program'], row['latency'], row['gap']) for row in rows}:
            same_case = [row for row in rows if (row['program'], row['latency'], row['gap']) == key]
            require(len(same_case) == len(participants) and
                    {row['version'] for row in same_case} == participants,
                    f'Incomplete comparison: {comparison}, {key}')
            require(len({row['instret'] for row in same_case}) == 1, f'Different instruction counts: {comparison}, {key}')
        rows_checked += len(rows)

    links_checked = 0
    for document in markdown_files():
        for target in re.findall(r'!?\[[^\]]*\]\(([^\s)]+)(?:\s+[^)]*)?\)', document.read_text()):
            target = target.strip('<>')
            if target.startswith('#') or re.match(r'^[A-Za-z][A-Za-z0-9+.-]*:', target):
                continue
            target = unquote(target.split('#', 1)[0])
            path = document.parent / target
            require(path.exists(), f'Broken local link: {document.relative_to(ROOT)} -> {target}')
            links_checked += 1
    print(f'REPOSITORY PASS: {len(versions)} versions, {len(manifest["files"])} frozen files, '
          f'{len(comparisons)} comparison archives / {rows_checked} rows, {links_checked} local links')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError) as error:
        raise SystemExit(f'REPOSITORY FAIL: {error}')
