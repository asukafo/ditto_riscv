"""Prove the checker rejects damaged real traces, not just accepts good ones."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from reference import FIELDS, Fault, Reference, verify


class CheckerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = Path("build/load_add_store.bin").read_bytes()
        cls.records = [json.loads(line) for line in Path("build/load_add_store-l1-g0.trace.jsonl").read_text().splitlines()]
        cls.ram = Path("build/load_add_store-l1-g0.trace.jsonl.ram").read_bytes()

    def rejected(self, records, memory=None):
        with self.assertRaises(ValueError):
            verify(self.image, records, self.ram if memory is None else memory)

    def test_valid_trace_and_known_program_results(self):
        self.assertEqual(verify(self.image, self.records, self.ram), 32)
        values = [int.from_bytes(self.ram[a:a+8], "little") for a in range(0x1000, 0x1020, 8)]
        self.assertEqual(values, [11, 12, 13, 14])
        branches = [r for r in self.records[:-1] if r["pc"] == 0x20]
        self.assertEqual([r["next_pc"] for r in branches], [0xc, 0xc, 0xc, 0x24])

    def test_every_architectural_field_is_checked(self):
        for field in FIELDS:
            with self.subTest(field=field):
                records = deepcopy(self.records)
                records[3][field] ^= 1  # first LD
                self.rejected(records)

    def test_first_divergence_names_instruction_and_field(self):
        records = deepcopy(self.records)
        records[3]["wdata"] = 99
        with self.assertRaisesRegex(ValueError, r"commit #4 PC=0xc \(ld\): wdata"):
            verify(self.image, records, self.ram)

    def test_corrupt_store_payload(self):
        records = deepcopy(self.records)
        records[5]["mem_data"] = 99
        self.rejected(records)

    def test_missing_duplicate_and_reordered_commits(self):
        for replacement in [self.records[:3] + self.records[4:],
                            self.records[:4] + self.records[3:],
                            self.records[:3] + [self.records[4], self.records[3]] + self.records[5:]]:
            self.rejected(replacement)

    def test_incomplete_or_extra_records(self):
        self.rejected(self.records[:-1])
        self.rejected(self.records[:3] + [self.records[-1]])
        self.rejected(self.records + [self.records[0]])
        self.rejected(self.records[:-1] + [self.records[0], self.records[-1]])

    def test_halt_metadata(self):
        for field, value in [("fault", 1), ("instret", 29), ("cycles", 0),
                             ("trap_pc",1), ("trap_cause",1), ("trap_value",1), ("exit_status",1)]:
            with self.subTest(field=field):
                records = deepcopy(self.records)
                records[-1][field] = value
                self.rejected(records)

    def test_cycle_order(self):
        records = deepcopy(self.records)
        records[1]["cycle"] = records[0]["cycle"] - 1
        self.rejected(records)

    def test_missing_field(self):
        records = deepcopy(self.records)
        del records[3]["wdata"]
        self.rejected(records)

    def test_wrong_type(self):
        records = deepcopy(self.records)
        records[3]["wdata"] = True  # bool must not masquerade as integer 1
        self.rejected(records)

    def test_final_memory_not_just_store_trace(self):
        memory = bytearray(self.ram)
        memory[0x1000] ^= 1
        self.rejected(self.records, memory)
        self.rejected(self.records, memory[:-1])

    def test_reference_x0_and_modular_arithmetic(self):
        # addi x0,x0,123; addi x5,x0,-1; addi x5,x5,1; ebreak
        image = b"".join(i.to_bytes(4, "little") for i in [0x07b00013, 0xfff00293, 0x00128293, 0x00100073])
        model = Reference(image)
        event, _ = model.step()
        self.assertEqual((event["rd_wen"], event["rd"], event["wdata"]), (0, 0, 0))
        event, _ = model.step()
        self.assertEqual(event["wdata"], (1 << 64) - 1)
        event, _ = model.step()
        self.assertEqual(event["wdata"], 0)
        self.assertEqual(model.regs[0], 0)

    def test_ecall_and_ebreak_do_not_retire(self):
        for instruction,code,cause in [(0x73,4,11),(0x100073,5,3)]:
            with self.subTest(instruction=instruction):
                model=Reference(instruction.to_bytes(4,"little"))
                with self.assertRaises(Fault) as raised:
                    model.step()
                self.assertEqual((raised.exception.code,raised.exception.cause,raised.exception.pc),(code,cause,0))
                self.assertEqual(model.pc,0)
                self.assertEqual(model.regs,[0]*32)


if __name__ == "__main__":
    unittest.main()
