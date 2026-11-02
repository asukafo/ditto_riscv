"""Mutation tests for the native verifier's new privilege/trap/C/atomic fields."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from reference import verify


def fixture(name):
    trace=Path(f"build/{name}-native-l1-g0.trace.jsonl")
    return (Path(f"build/{name}.bin").read_bytes(),[json.loads(x) for x in trace.read_text().splitlines()],Path(str(trace)+".ram").read_bytes())


class NativeChecker(unittest.TestCase):
    def test_native_valid_and_new_fields(self):
        image,records,ram=fixture("native_compressed")
        self.assertGreater(verify(image,records,ram),30)
        for field in ("bytes","privilege","mem_atomic","mem_amo"):
            with self.subTest(field=field):
                broken=deepcopy(records)
                next(r for r in broken if r["kind"]=="commit")[field]^=1
                with self.assertRaises(ValueError): verify(image,broken,ram)

    def test_all_trap_fields(self):
        image,records,ram=fixture("machine_demo")
        for field in ("pc","cause","value","target","privilege"):
            with self.subTest(field=field):
                broken=deepcopy(records)
                next(r for r in broken if r["kind"]=="trap")[field]^=1
                with self.assertRaises(ValueError): verify(image,broken,ram)

    def test_missing_or_duplicate_trap(self):
        image,records,ram=fixture("machine_demo")
        i=next(i for i,r in enumerate(records) if r["kind"]=="trap")
        for broken in (records[:i]+records[i+1:],records[:i]+[records[i]]+records[i:]):
            with self.assertRaises(ValueError): verify(image,broken,ram)

    def test_irq_input_is_required(self):
        image,records,ram=fixture("irq_external")
        broken=deepcopy(records)
        for record in broken:
            if record["kind"]=="input": record["irq"]=0
        with self.assertRaises(ValueError): verify(image,broken,ram)

    def test_mmio_acceptance_time_is_checked(self):
        image,records,ram=fixture("native_mmio_time")
        broken=deepcopy(records)
        next(r for r in broken if r["kind"]=="mmio_read")["cycle"]+=1
        with self.assertRaises(ValueError): verify(image,broken,ram)

    def test_translated_physical_memory_checked(self):
        image,records,ram=fixture("sv39_atomic_alias")
        broken=bytearray(ram); broken[0x2000]^=1
        with self.assertRaises(ValueError): verify(image,records,broken)
        with self.assertRaises(ValueError): verify(image,records,ram[:-1])

    def test_missing_native_halt(self):
        image,records,ram=fixture("full_demo")
        with self.assertRaises(ValueError): verify(image,records[:-1],ram)


if __name__=="__main__": unittest.main()
