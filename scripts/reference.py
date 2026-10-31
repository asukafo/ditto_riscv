"""Instruction-level oracle for this project's documented RV64 subset.

No RTL signals, simulation cycles, or simulator RAM are used to execute instructions.
This is a small teaching model, not Spike or a complete RISC-V compliance model.
"""
import argparse
import json
from pathlib import Path

MASK = (1 << 64) - 1
FIELDS = ("pc", "insn", "next_pc", "rd_wen", "rd", "wdata",
          "mem_valid", "mem_write", "mem_addr", "mem_data")


def signed(value, width):
    return value - (1 << width) if value & (1 << (width - 1)) else value


class Fault(Exception):
    def __init__(self, code):
        self.code = code


class Reference:
    def __init__(self, image):
        if len(image) > 65536:
            raise ValueError("image exceeds 64 KiB RAM")
        self.ram = bytearray(65536)
        self.ram[:len(image)] = image
        self.regs = [0] * 32
        self.pc = 0
        self.stopped = False

    def read(self, address):
        # Match the documented bus boundary: every transaction returns eight bytes.
        if not 0 <= address <= len(self.ram) - 8:
            raise Fault(3)
        return int.from_bytes(self.ram[address:address + 8], "little")

    def step(self):
        if self.stopped:
            raise ValueError("extra commit after EBREAK")
        pc = self.pc
        instruction = self.read(pc) & 0xffffffff
        opcode = instruction & 127
        destination = (instruction >> 7) & 31
        function = (instruction >> 12) & 7
        source1 = self.regs[(instruction >> 15) & 31]
        source2 = self.regs[(instruction >> 20) & 31]
        upper = instruction >> 25
        following = (pc + 4) & MASK
        event = dict.fromkeys(FIELDS, 0)
        event.update(pc=pc, insn=instruction)
        result = None
        address = None
        store = False
        stop = False
        if opcode == 0x13:
            immediate = signed(instruction >> 20, 12)
            amount = (instruction >> 20) % 64
            if function == 1 and instruction >> 26 == 0:
                result, name = source1 << amount, "slli"
            elif function == 5 and instruction >> 26 in (0, 16):
                arithmetic = instruction >> 26 == 16
                result = (signed(source1, 64) if arithmetic else source1) >> amount
                name = "srai" if arithmetic else "srli"
            elif function in (0, 2, 3, 4, 6, 7):
                operations = {0: (source1 + immediate, "addi"),
                              2: (int(signed(source1, 64) < immediate), "slti"),
                              3: (int(source1 < (immediate & MASK)), "sltiu"),
                              4: (source1 ^ immediate, "xori"),
                              6: (source1 | immediate, "ori"),
                              7: (source1 & immediate, "andi")}
                result, name = operations[function]
            else:
                raise Fault(1)
        elif opcode == 0x33:
            if upper == 32 and function in (0, 5):
                result, name = ((source1 - source2, "sub") if function == 0 else
                                (signed(source1, 64) >> (source2 % 64), "sra"))
            elif upper == 0:
                operations = {0: (source1 + source2, "add"),
                              1: (source1 << (source2 % 64), "sll"),
                              2: (int(signed(source1, 64) < signed(source2, 64)), "slt"),
                              3: (int(source1 < source2), "sltu"),
                              4: (source1 ^ source2, "xor"),
                              5: (source1 >> (source2 % 64), "srl"),
                              6: (source1 | source2, "or"),
                              7: (source1 & source2, "and")}
                result, name = operations[function]
            else:
                raise Fault(1)
        elif opcode == 0x37:
            result = signed(instruction & 0xfffff000, 32)
            name = "lui"
        elif opcode == 0x6f:
            offset = (((instruction >> 31) << 20) | (((instruction >> 12) & 255) << 12)
                      | (((instruction >> 20) & 1) << 11) | (((instruction >> 21) & 1023) << 1))
            following = (pc + signed(offset, 21)) & MASK
            result = pc + 4
            name = "jal"
        elif opcode == 0x63 and function in (0, 1, 4, 5, 6, 7):
            predicates = {0: source1 == source2, 1: source1 != source2,
                          4: signed(source1, 64) < signed(source2, 64),
                          5: signed(source1, 64) >= signed(source2, 64),
                          6: source1 < source2, 7: source1 >= source2}
            offset = (((instruction >> 31) << 12) | (((instruction >> 7) & 1) << 11)
                      | (((instruction >> 25) & 63) << 5) | (((instruction >> 8) & 15) << 1))
            if predicates[function]:
                following = (pc + signed(offset, 13)) & MASK
            name = {0: "beq", 1: "bne", 4: "blt", 5: "bge", 6: "bltu", 7: "bgeu"}[function]
        elif opcode in (0x03, 0x23) and function == 3:
            store = opcode == 0x23
            offset = ((instruction >> 25) << 5) | ((instruction >> 7) & 31) if store else instruction >> 20
            address = (source1 + signed(offset, 12)) & MASK
            name = "sd" if store else "ld"
        elif instruction == 0x00100073:
            name = "ebreak"
            stop = True
        else:
            raise Fault(1)
        # No register/PC/memory side effects before validation succeeds.
        if following % 4 or (address is not None and address % 8):
            raise Fault(2)
        if address is not None:
            old = self.read(address)  # bounds validation applies to both LD and SD
            data = source2 if store else old
            event.update(mem_valid=1, mem_write=int(store), mem_addr=address, mem_data=data)
            if store:
                self.ram[address:address + 8] = data.to_bytes(8, "little")
            else:
                result = data
        if result is not None and destination != 0:
            self.regs[destination] = result & MASK
            event.update(rd_wen=1, rd=destination, wdata=result & MASK)
        self.regs[0] = 0
        self.pc = following
        self.stopped = stop
        event["next_pc"] = following
        return event, name


def verify(image, records, memory, show=0):
    model = Reference(image)
    commits = 0
    last_cycle = 0
    terminal = False
    for record in records:
        if terminal:
            raise ValueError("records present after halt")
        if record.get("kind") == "halt":
            terminal = True
            if not model.stopped:
                try:
                    model.step()
                except Fault as fault:
                    expected_fault = fault.code
                else:
                    raise ValueError(f"trace ended before instruction at PC=0x{model.pc:x} committed")
            else:
                expected_fault = 0
            if record.get("fault") != expected_fault:
                raise ValueError(f"halt fault: RTL={record.get('fault')} reference={expected_fault}")
            if record.get("instret") != commits:
                raise ValueError("halt instret does not match number of commits")
            cycles = record.get("cycles")
            if not isinstance(cycles, int) or cycles < last_cycle or cycles < 1:
                raise ValueError("invalid final cycle count")
            if expected_fault and cycles <= last_cycle:
                raise ValueError("fault must occur after the last successful commit")
            continue
        if record.get("kind") != "commit":
            raise ValueError("unknown trace record kind")
        try:
            expected, name = model.step()
        except Fault as fault:
            raise ValueError(f"commit #{commits + 1} at PC=0x{model.pc:x}: expected fault {fault.code}") from None
        for field in FIELDS:
            actual = record.get(field)
            if type(actual) is not int or actual != expected[field]:
                raise ValueError(f"commit #{commits + 1} PC=0x{expected['pc']:x} ({name}): "
                                 f"{field}: RTL={actual!r}, reference={expected[field]} (0x{expected[field]:x})")
        cycle = record.get("cycle")
        if type(cycle) is not int or cycle <= last_cycle:
            raise ValueError("commit cycles must strictly increase")
        last_cycle = cycle
        commits += 1
        if commits <= show:
            change = f"x{expected['rd']}=0x{expected['wdata']:x}" if expected["rd_wen"] else "no register write"
            access = ""
            if expected["mem_valid"]:
                access = f"; {'store' if expected['mem_write'] else 'load'} [0x{expected['mem_addr']:x}]=0x{expected['mem_data']:x}"
            print(f"#{commits:03} C{cycle:<5} PC=0x{expected['pc']:04x} {name:<6} {change}{access}; next=0x{expected['next_pc']:x}")
    if not terminal:
        raise ValueError("missing halt record")
    if len(memory) != len(model.ram):
        raise ValueError("RAM snapshot size differs from reference")
    if memory != model.ram:
        address = next(i for i, (a, b) in enumerate(zip(memory, model.ram)) if a != b)
        raise ValueError(f"final RAM differs at 0x{address:x}: RTL=0x{memory[address]:02x}, reference=0x{model.ram[address]:02x}")
    return commits


def verify_files(image, trace, show=0):
    records = [json.loads(line) for line in Path(trace).read_text().splitlines() if line.strip()]
    return verify(Path(image).read_bytes(), records, Path(str(trace) + ".ram").read_bytes(), show)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--trace", required=True)
    parser.add_argument("--show", type=int, default=0)
    args = parser.parse_args()
    try:
        count = verify_files(args.image, args.trace, args.show)
    except (ValueError, OSError) as error:
        parser.exit(1, f"DIFF FAIL: {error}\n")
    print(f"DIFF PASS: {count} commits, halt status and all 65536 RAM bytes match")
