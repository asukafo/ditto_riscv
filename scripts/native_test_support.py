"""Shared driver for actual native RTL simulation and independent reference checks."""
import json
import os
from pathlib import Path
import subprocess
from reference import verify_files


class NativeSuite:
    def __init__(self,cross="riscv64-elf-"):
        self.cross=cross; self.runs=0; self.commits=0; self.traps=0
        self.simulator=os.environ.get("SIMULATOR","build/full_obj/Vrv64_core")

    def compile(self,name,body,data="",compressed=False):
        mode="rvc" if compressed else "norvc"
        Path(f"build/{name}.S").write_text(f'.option {mode}\n.option norelax\n.include "sw/finish.inc"\n.section .text\n.global _start\n_start:\n{body}\n{data}\n')
        subprocess.run([self.cross+"gcc","-march=rv64imac_zicsr_zifencei","-mabi=lp64","-nostdlib",
                        "-Wl,-Ttext=0,-e,_start,--no-relax","-o",f"build/{name}.elf",f"build/{name}.S"],check=True)
        subprocess.run([self.cross+"objcopy","-O","binary","-j",".text",f"build/{name}.elf",f"build/{name}.bin"],check=True)

    def run(self,name,signature=None,causes=None,timings=None,events=None):
        results=[]
        for latency,gap in timings or [(1,0),(5,3)]:
            trace=f"build/{name}-native-l{latency}-g{gap}.trace.jsonl"
            event_file="-"
            if events:
                event_file=f"build/{name}.irq.txt"
                Path(event_file).write_text("\n".join(f"{cycle} {mask:#x}" for cycle,mask in events)+"\n")
            process=subprocess.run([self.simulator,f"build/{name}.bin",str(latency),"-",str(gap),trace,event_file],capture_output=True,text=True)
            assert process.returncode==0,(name,latency,gap,process.stdout,process.stderr)
            count=verify_files(f"build/{name}.bin",trace)
            records=[json.loads(line) for line in Path(trace).read_text().splitlines()]
            ram=Path(trace+".ram").read_bytes()
            traps=[r for r in records if r["kind"]=="trap"]
            if signature is not None: assert int.from_bytes(ram[512:520],"little")==signature,(name,signature)
            if causes is not None: assert [r["cause"] for r in traps]==causes,(name,[r["cause"] for r in traps],causes)
            self.runs+=1; self.commits+=count; self.traps+=len(traps)
            results.append((records,ram))
        return results


def words(memory,address,count):
    return [int.from_bytes(memory[address+8*i:address+8*i+8],"little") for i in range(count)]
