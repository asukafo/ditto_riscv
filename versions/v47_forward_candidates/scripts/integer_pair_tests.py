"""Exercise every supported integer operation as a real second retirement."""
from native_test_support import NativeSuite
from reference import PAIR_INTEGER_NAMES


def main():
    immediate = "addi slti sltiu xori ori andi slli srli srai addiw slliw srliw sraiw"
    register = "add sub sll slt sltu xor srl sra or and addw subw sllw srlw sraw"
    operands = {op: "t4,t0,3" for op in immediate.split()}
    operands.update({op: "t4,t0,t1" for op in register.split()})
    operands.update(lui="t4,0x80000", auipc="t4,0xfffff")
    assert set(operands) == PAIR_INTEGER_NAMES

    body = ["li t0,-123", "li t1,63", "li t3,0", ".balign 8"]
    for op, args in operands.items():
        body.extend(("addi t3,t3,1", f"{op} {args}"))
    body.extend(("sd t3,512(zero)", "SIM_EXIT"))
    suite = NativeSuite()
    suite.compile("integer_pair", "\n".join(body))
    for records, _ in suite.run("integer_pair", signature=len(operands), causes=[],
                                timings=[(1,0),(5,0),(5,3),(20,7)]):
        lane_two = [r for r in records if r.get("retire_slot") == 1 and r["rd"] == 29]
        expected_pcs = [20 + i*8 for i in range(len(operands))]
        assert [r["pc"] for r in lane_two] == expected_pcs, lane_two
    print(f"INTEGER PAIR PASS: {len(operands)} operations retired in lane two in each of {suite.runs} timing cases")


if __name__ == "__main__":
    main()
