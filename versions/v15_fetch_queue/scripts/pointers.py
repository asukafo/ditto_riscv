"""A reproducible, nonsequential single cycle through 64 nodes, starting at 0."""
from pathlib import Path
import random
import struct

order = list(range(1, 64))
random.Random(20261030).shuffle(order)
order = [0] + order
following = {node: order[(i + 1) % 64] for i, node in enumerate(order)}
Path("build").mkdir(exist_ok=True)
Path("build/pointers.bin").write_bytes(b"".join(
    struct.pack("<QQ", 0x1000 + following[node] * 16, node)
    for node in range(64)))
