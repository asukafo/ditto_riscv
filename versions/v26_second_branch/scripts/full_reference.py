"""Independent instruction-level RV64IMAC + M/S/U/Sv39 model for native traces.

Clock counts, IRQ levels and MMIO read acceptance times are simulation inputs;
register values, translations, arithmetic results and trap decisions are computed here.
"""
from collections import deque
from reference import Reference, Fault, FIELDS, MASK, signed

EXTRA=("bytes","privilege","mem_atomic","mem_amo")
FIXED=0xa00000000
STATUS_MASK=0x7e19aa


def decompress(c):
    def bits(hi,lo=0): return (c>>lo)&((1<<(hi-lo+1))-1)
    def it(op,rd,rs,f,imm): return ((imm&4095)<<20)|(rs<<15)|(f<<12)|(rd<<7)|op
    def rt(op,rd,rs,rs2,f,upper=0): return (upper<<25)|(rs2<<20)|(rs<<15)|(f<<12)|(rd<<7)|op
    def st(rs,rs2,f,imm): return ((imm>>5)<<25)|(rs2<<20)|(rs<<15)|(f<<12)|((imm&31)<<7)|0x23
    def j(imm):
        imm &= (1<<21)-1
        return (((imm>>20)&1)<<31)|(((imm>>1)&1023)<<21)|(((imm>>11)&1)<<20)|(((imm>>12)&255)<<12)|0x6f
    def br(rs,f,imm):
        imm &= 8191
        return (((imm>>12)&1)<<31)|(((imm>>5)&63)<<25)|(rs<<15)|(f<<12)|(((imm>>1)&15)<<8)|(((imm>>11)&1)<<7)|0x63
    q=c&3; major=c>>13; rd=bits(11,7); rs2=bits(6,2); p1=8+bits(9,7); p2=8+bits(4,2)
    imm=signed((bits(12,12)<<5)|bits(6,2),6)
    if q==0:
        if major==0:
            off=(bits(10,7)<<6)|(bits(12,11)<<4)|(bits(5,5)<<3)|(bits(6,6)<<2)
            if not off: raise ValueError("reserved C.ADDI4SPN")
            return it(0x13,p2,2,0,off)
        if major in (2,3,6,7):
            double=major&1
            off=((bits(6,5)<<6)|(bits(12,10)<<3)) if double else ((bits(5,5)<<6)|(bits(12,10)<<3)|(bits(6,6)<<2))
            return it(3,p2,p1,3 if double else 2,off) if major<4 else st(p1,p2,3 if double else 2,off)
    elif q==1:
        if major in (0,1,2):
            if major==1 and rd==0: raise ValueError("reserved C.ADDIW")
            return it(0x1b if major==1 else 0x13,rd,0 if major==2 else rd,0,imm)
        if major==3:
            if rd==2:
                off=(bits(12,12)<<9)|(bits(4,3)<<7)|(bits(5,5)<<6)|(bits(2,2)<<5)|(bits(6,6)<<4)
                if not off: raise ValueError("reserved C.ADDI16SP")
                return it(0x13,2,2,0,signed(off,10))
            if not imm: raise ValueError("reserved C.LUI")
            return ((imm&0xfffff)<<12)|(rd<<7)|0x37
        if major==4:
            mode=bits(11,10)
            if mode<2: return it(0x13,p1,p1,5,((0x400 if mode else 0)|((bits(12,12)<<5)|bits(6,2))))
            if mode==2: return it(0x13,p1,p1,7,imm)
            fun=bits(6,5)
            if not bits(12,12): return rt(0x33,p1,p1,p2,[0,4,6,7][fun],0x20 if fun==0 else 0)
            if fun<2: return rt(0x3b,p1,p1,p2,0,0x20 if fun==0 else 0)
        if major==5:
            off=(bits(12,12)<<11)|(bits(8,8)<<10)|(bits(10,9)<<8)|(bits(6,6)<<7)|(bits(7,7)<<6)|(bits(2,2)<<5)|(bits(11,11)<<4)|(bits(5,3)<<1)
            return j(signed(off,12))
        if major in (6,7):
            off=(bits(12,12)<<8)|(bits(6,5)<<6)|(bits(2,2)<<5)|(bits(11,10)<<3)|(bits(4,3)<<1)
            return br(p1,major-6,signed(off,9))
    elif q==2:
        if major==0: return it(0x13,rd,rd,1,(bits(12,12)<<5)|bits(6,2))
        if major in (2,3):
            if not rd: raise ValueError("reserved C load SP")
            off=((bits(4,2)<<6)|(bits(12,12)<<5)|(bits(6,5)<<3)) if major==3 else ((bits(3,2)<<6)|(bits(12,12)<<5)|(bits(6,4)<<2))
            return it(3,rd,2,major,off)
        if major==4:
            if rs2: return rt(0x33,rd,rd if bits(12,12) else 0,rs2,0)
            if rd: return it(0x67,1 if bits(12,12) else 0,rd,0,0)
            if bits(12,12): return 0x100073
        if major in (6,7):
            off=((bits(9,7)<<6)|(bits(12,10)<<3)) if major==7 else ((bits(8,7)<<6)|(bits(12,9)<<2))
            return st(2,rs2,3 if major==7 else 2,off)
    raise ValueError(f"unsupported/reserved compressed instruction 0x{c:04x}")


class FullReference(Reference):
    def __init__(self,image):
        super().__init__(image)
        self.pc_alignment=2
        self.priv=3
        self.csr={a:0 for a in (0x100,0x104,0x105,0x106,0x140,0x141,0x142,0x143,0x144,0x180,
                                0x300,0x302,0x303,0x304,0x305,0x306,0x320,0x340,0x341,0x342,0x343,0x344,0xb00,0xb02)}
        self.csr[0x300]=FIXED
        self.irq=0; self.clock=0; self.edge=0; self.reservation=None; self.invalidate=False
        self.last_trap=(0,0,0); self._fetched=None; self.pending_write=None
        self.msip=0; self.mtimecmp=MASK; self.mmio_reads=deque()

    def advance(self,target):
        if target<self.clock: raise ValueError("clock moved backwards")
        if not self.csr[0x320]&1: self.csr[0xb00]=(self.csr[0xb00]+target-self.clock)&MASK
        self.clock=target

    def prepare(self,cycle):
        self.advance(max(self.clock,cycle-1)); self.edge=cycle; self.pending_write=None; self._fetched=None

    def finish(self,retired):
        inhibit=self.csr[0x320]
        self.advance(self.edge)
        if retired and not inhibit&4: self.csr[0xb02]=(self.csr[0xb02]+1)&MASK
        if self.pending_write is not None: self.write_csr(*self.pending_write)
        self.pending_write=None; self._fetched=None

    def effective_priv(self,fetch=False):
        s=self.csr[0x300]
        return ((s>>11)&3) if self.priv==3 and s&(1<<17) and not fetch else self.priv

    def physical_read(self,address,size,store=False,fetch=False):
        if address in (0x2000000,0x2004000,0x200bff8) and not fetch:
            if store: return 0
            if not self.mmio_reads: raise ValueError("missing MMIO acceptance time")
            event=self.mmio_reads.popleft()
            if event["address"]!=address or event["size"]!=size: raise ValueError("MMIO address/width mismatch")
            data=self.msip if address==0x2000000 else self.mtimecmp if address==0x2004000 else event["cycle"]
            return data&((1<<(8*size))-1)
        return Reference.read(self,address,size,store,fetch)

    def translate(self,address,store=False,fetch=False):
        priv=self.effective_priv(fetch)
        satp=self.csr[0x180]
        if priv==3 or satp>>60!=8: return address
        page_cause=12 if fetch else 15 if store else 13
        def fail(): raise Fault(3,page_cause,self.pc,address)
        if address>>39 != ((1<<25)-1 if address&(1<<38) else 0): fail()
        base=(satp&((1<<44)-1))*4096
        for level in (2,1,0):
            pte_address=base+((address>>(12+9*level))&511)*8
            try: pte=Reference.read(self,pte_address,8)
            except Fault: raise Fault(3,1 if fetch else 7 if store else 5,self.pc,address) from None
            valid,read,write,execute,user,accessed,dirty=[bool(pte&(1<<n)) for n in (0,1,2,3,4,6,7)]
            if not valid or (write and not read) or pte>>54: fail()
            ppn=(pte>>10)&((1<<44)-1)
            if read or execute:
                status=self.csr[0x300]
                if (priv==0 and not user) or (priv==1 and user and (fetch or not status&(1<<18))): fail()
                if fetch and not execute: fail()
                if store and not write: fail()
                if not store and not fetch and not (read or (status&(1<<19) and execute)): fail()
                if not accessed or (store and not dirty): fail() # Svade
                if ppn% (1<<(9*level)): fail()
                mask=(1<<(12+9*level))-1
                return ((ppn*4096)&~mask)|(address&mask)
            if level==0 or user or accessed or dirty: fail()
            base=ppn*4096
        fail()

    def read(self,address,size=8,store=False,fetch=False):
        physical=self.translate(address,store,fetch)
        try: return self.physical_read(physical,size,store,fetch)
        except Fault as error: raise Fault(error.code,error.cause,self.pc,address) from None

    def write_memory(self,address,data,size):
        physical=self.translate(address,True)
        self.last_physical_store=(address,physical)
        self.reservation=None
        if physical==0x2000000 and size<=4: self.msip=data&1; return
        if physical==0x2004000 and size<=8:
            mask=(1<<(8*size))-1; self.mtimecmp=(self.mtimecmp&~mask)|(data&mask); return
        if physical==0x200bff8: raise Fault(3,7,self.pc,address)
        Reference.write_memory(self,physical,data,size)

    def is_exit_address(self,address):
        return self.last_physical_store==(address,0xfff0)

    def fetch(self):
        if self._fetched is not None: return self._fetched
        low=self.read(self.pc,2,fetch=True)
        if low&3!=3:
            try: expanded=decompress(low)
            except ValueError: raise Fault(1,2,self.pc,low) from None
            self._fetched=(expanded,low,2)
        else:
            high=self.read((self.pc+2)&MASK,2,fetch=True)
            self._fetched=(low|(high<<16),low|(high<<16),4)
        return self._fetched

    def read_csr(self,address,write):
        s=self.csr[0x300]; delegated=self.csr[0x303]
        pending=self.csr[0x344]|(self.irq&0xaaa)
        special={0x100:s&0x3000c0122,0x104:self.csr[0x304]&delegated,0x144:pending&delegated,
                 0x301:0x8000000000141105,0x344:pending,0xc00:self.csr[0xb00],0xc01:self.edge,0xc02:self.csr[0xb02],
                 0xf11:0,0xf12:0,0xf13:0,0xf14:0,0xf15:0}
        if address not in self.csr and address not in special: raise ValueError("unknown CSR")
        if self.priv<((address>>8)&3) or (write and address>>10==3): raise ValueError("CSR privilege/read-only")
        if address==0x180 and self.priv==1 and s&(1<<20): raise ValueError("TVM")
        if address in (0xc00,0xc01,0xc02) and self.priv!=3:
            index=address&3
            if not self.csr[0x306]&(1<<index) or (self.priv==0 and not self.csr[0x106]&(1<<index)): raise ValueError("counter denied")
        return special[address] if address in special else self.csr[address]

    def write_csr(self,address,data):
        data&=MASK
        if address==0x301: return # fixed WARL ISA features
        if address==0x100: self.csr[0x300]=(self.csr[0x300]&~0xc0122)|(data&0xc0122)|FIXED
        elif address==0x104: self.csr[0x304]=(self.csr[0x304]&~self.csr[0x303])|(data&self.csr[0x303])
        elif address in (0x105,0x305): self.csr[address]=(data&~3)|(1 if data&3==1 else 0)
        elif address in (0x106,0x306): self.csr[address]=data&7
        elif address in (0x141,0x341): self.csr[address]=data&~1
        elif address==0x144: self.csr[0x344]=(self.csr[0x344]&~(self.csr[0x303]&2))|(data&self.csr[0x303]&2)
        elif address==0x180:
            if data>>60 in (0,8): self.csr[address]=(data&((1<<44)-1))|((data>>60)<<60)
        elif address==0x300:
            self.csr[address]=(data&STATUS_MASK)|FIXED
            if (data>>11)&3==2: self.csr[address]&=~(3<<11)
        elif address==0x302: self.csr[address]=data&0xb3ff
        elif address==0x303: self.csr[address]=data&0x222
        elif address==0x304: self.csr[address]=data&0xaaa
        elif address==0x320: self.csr[address]=data&5
        elif address==0x344: self.csr[address]=data&0x222
        else: self.csr[address]=data

    def irq_cause(self):
        s=self.csr[0x300]
        pending=(self.csr[0x344]|self.irq)&self.csr[0x304]
        for n in (11,3,7,9,1,5):
            delegated=bool(self.csr[0x303]&(1<<n))
            enabled=(self.priv==0 or (self.priv==1 and bool(s&2))) if delegated else (self.priv<3 or bool(s&8))
            if enabled and pending&(1<<n): return (1<<63)|n
        return None

    def take_trap(self,fault):
        cause=fault.cause; s=self.csr[0x300]; n=cause&~(1<<63)
        delegation=self.csr[0x303 if cause>>63 else 0x302]
        delegated=self.priv!=3 and n<64 and bool(delegation&(1<<n))
        prefix=0x100 if delegated else 0x300
        self.csr[prefix+0x41]=fault.pc&~1
        self.csr[prefix+0x42]=cause; self.csr[prefix+0x43]=fault.value
        if delegated:
            self.csr[0x300]=(s&~((1<<5)|(1<<1)|(1<<8)))|(((s>>1)&1)<<5)|(int(self.priv==1)<<8)
        else:
            self.csr[0x300]=(s&~((1<<7)|(1<<3)|(3<<11)))|(((s>>3)&1)<<7)|(self.priv<<11)
        self.priv=1 if delegated else 3
        vector=self.csr[prefix+5]
        self.pc=(vector&~3)+(n*4 if cause>>63 and vector&3==1 else 0)
        self.last_trap=(fault.pc,cause,fault.value); self.reservation=None
        return self.pc

    def step(self,cycle):
        self.prepare(cycle)
        instruction,raw,length=self.fetch()
        pc=self.pc; old_priv=self.priv; op=instruction&127; f=(instruction>>12)&7; upper=instruction>>25
        rd=(instruction>>7)&31; rs1=(instruction>>15)&31; rs2=(instruction>>20)&31
        a=self.regs[rs1]; b=self.regs[rs2]; following=(pc+length)&MASK
        event=dict.fromkeys(FIELDS+EXTRA,0); event.update(pc=pc,insn=raw,bytes=length,privilege=old_priv,next_pc=following)
        result=None
        def illegal(): raise Fault(1,2,pc,raw)
        if op in (0x33,0x3b) and upper==1:
            word=op==0x3b
            if word and f in (1,2,3): illegal()
            width=32 if word else 64; mask=(1<<width)-1; ua=a&mask; ub=b&mask
            sa=signed(ua,width); sb=signed(ub,width)
            names=["mul","mulh","mulhsu","mulhu","div","divu","rem","remu"]
            name=names[f]+("w" if word else "")
            if f==0: result=ua*ub
            elif f==1: result=(sa*sb)>>64
            elif f==2: result=(sa*ub)>>64
            elif f==3: result=(ua*ub)>>64
            else:
                left,right=(sa,sb) if f in (4,6) else (ua,ub)
                if not right: quotient=mask; remainder=left
                else:
                    quotient=abs(left)//abs(right)
                    if (left<0)!=(right<0): quotient=-quotient
                    remainder=left-quotient*right
                result=remainder if f>=6 else quotient
            if word: result=signed(result&0xffffffff,32)
        elif op==0x2f:
            fun=instruction>>27; size=4 if f==2 else 8 if f==3 else 0
            if not size or fun not in (0,1,2,3,4,8,12,16,20,24,28) or (fun==2 and rs2): illegal()
            write=fun!=2
            if a%size: raise Fault(2,6 if write else 4,pc,a)
            physical=self.translate(a,write)
            if physical>=0x10000: raise Fault(3,7 if write else 5,pc,a)
            mask=(1<<(8*size))-1
            old=int.from_bytes(self.ram[physical:physical+size],"little")
            event.update(mem_valid=1,mem_addr=a,mem_size=size.bit_length()-1,mem_atomic=1,mem_amo=fun)
            if fun==2:
                self.reservation=None if self.invalidate else (physical,size); result=signed(old,8*size); event["mem_data"]=old; name="lr"
            elif fun==3:
                success=self.reservation==(physical,size); self.reservation=None; result=0 if success else 1
                event.update(mem_write=int(success),mem_data=(b&mask) if success else 0)
                if success: self.ram[physical:physical+size]=(b&mask).to_bytes(size,"little")
                name="sc"
            else:
                rhs=b&mask
                values={0:old+rhs,1:rhs,4:old^rhs,8:old|rhs,12:old&rhs,
                        16:old if signed(old,8*size)<signed(rhs,8*size) else rhs,
                        20:old if signed(old,8*size)>signed(rhs,8*size) else rhs,
                        24:min(old,rhs),28:max(old,rhs)}
                new=values[fun]&mask; self.ram[physical:physical+size]=new.to_bytes(size,"little"); self.reservation=None
                event.update(mem_write=1,mem_data=new); result=signed(old,8*size); name="amo"
        elif op==0x73:
            if f:
                if f==4: illegal()
                address=instruction>>20; write=(f&3)==1 or rs1!=0
                try: result=self.read_csr(address,write)
                except ValueError: illegal()
                operand=rs1 if f&4 else a
                base=self.csr[0x344] if address==0x344 else self.csr[0x344]&self.csr[0x303] if address==0x144 else result
                value=operand if f&3==1 else base|operand if f&3==2 else base&~operand
                if write: self.pending_write=(address,value)
                name="csr"
            elif instruction in (0x73,0x100073):
                raise Fault(4 if instruction==0x73 else 5,11 if self.priv==3 else 9 if self.priv==1 else 8,pc,0) if instruction==0x73 else Fault(5,3,pc,0)
            elif instruction in (0x30200073,0x10200073):
                mret=instruction==0x30200073; status=self.csr[0x300]
                if (mret and self.priv!=3) or (not mret and (self.priv==0 or (self.priv==1 and status&(1<<22)))): illegal()
                following=self.csr[0x341 if mret else 0x141]
                self.priv=((status>>11)&3) if mret else ((status>>8)&1)
                if mret: status=(status&~((1<<3)|(1<<7)|(3<<11)))|(((status>>7)&1)<<3)|(1<<7)
                else: status=(status&~((1<<1)|(1<<5)|(1<<8)))|(((status>>5)&1)<<1)|(1<<5)
                if self.priv!=3: status&=~(1<<17)
                self.csr[0x300]=status; self.reservation=None; name="mret" if mret else "sret"
            elif instruction==0x10500073:
                if self.priv==0 or (self.priv==1 and self.csr[0x300]&(1<<21)): illegal()
                name="wfi"
            elif instruction>>25==9 and rd==0:
                if self.priv==0 or (self.priv==1 and self.csr[0x300]&(1<<20)): illegal()
                self.reservation=None; name="sfence.vma"
            else: illegal()
        elif op==0x0f and f==1: name="fence.i"
        else:
            try: base,name=Reference.step(self)
            except Fault as fault:
                if fault.code==1: fault.value=raw
                raise
            base.update(bytes=length,privilege=old_priv,mem_atomic=0,mem_amo=0)
            self.finish(True)
            return base,name
        if result is not None and rd:
            self.regs[rd]=result&MASK; event.update(rd_wen=1,rd=rd,wdata=result&MASK)
        self.regs[0]=0; self.pc=following; event["next_pc"]=following
        self.finish(True)
        return event,name


def verify_full(image,records,memory,show=0):
    model=FullReference(image); commits=0; terminal=False; last_cycle=0; last_slot=-1
    for record in records[1:]:
        kind=record.get("kind")
        if terminal: raise ValueError("record after halt")
        if kind=="input":
            model.irq=record["irq"]; model.invalidate=bool(record.get("invalidate",0))
            if model.invalidate: model.reservation=None
            continue
        if kind=="mmio_read": model.mmio_reads.append(record); continue
        if kind=="trap":
            cycle=record["cycle"]
            if cycle<=last_cycle: raise ValueError("unordered trap")
            if record["cause"]>>63:
                model.prepare(cycle)
                expected=model.irq_cause()
                if expected!=record["cause"]: raise ValueError(f"interrupt cause: {expected} != {record['cause']}")
                fault=Fault(0,expected,model.pc,0)
            else:
                try: model.step(cycle)
                except Fault as caught: fault=caught
                else: raise ValueError("RTL trapped on a legal instruction")
            model.finish(False); target=model.take_trap(fault)
            for key,value in dict(pc=fault.pc,cause=fault.cause,value=fault.value,target=target,privilege=model.priv).items():
                if record[key]!=value: raise ValueError(f"trap {key}: RTL={record[key]}, reference={value}")
            last_cycle=cycle;last_slot=-1
        elif kind=="commit":
            cycle=record["cycle"]
            slot=record.get('retire_slot',0)
            if cycle<last_cycle or (cycle==last_cycle and not(slot==1 and last_slot==0)) or (cycle>last_cycle and slot!=0):raise ValueError("unordered commit slot")
            last_slot=slot
            try: expected,name=model.step(cycle)
            except Fault as fault: raise ValueError(f"unexpected commit #{commits+1} at 0x{model.pc:x}, expected cause {fault.cause}") from None
            for key in FIELDS+EXTRA:
                if record.get(key)!=expected[key]: raise ValueError(f"commit #{commits+1} PC=0x{expected['pc']:x} {name} {key}: RTL={record.get(key)}, reference={expected[key]}")
            if slot==1 and name not in ("addi","add","sub"):raise ValueError("unsupported second-slot instruction")
            commits+=1; last_cycle=cycle
            if commits<=show: print(f"#{commits:03} C{cycle:<6} P{expected['privilege']} PC=0x{expected['pc']:x} {name} rd={expected['rd']} value=0x{expected['wdata']:x} next=0x{expected['next_pc']:x}")
        elif kind=="halt":
            terminal=True
            if not model.stopped or record["fault"] or record["exit_status"]!=model.exit_status: raise ValueError("native halt status mismatch")
            if record["instret"]!=commits or record["cycles"]!=last_cycle: raise ValueError("native final counters mismatch")
            actual=tuple(record[k] for k in ("trap_pc","trap_cause","trap_value"))
            if actual!=model.last_trap: raise ValueError("last trap metadata mismatch")
        else: raise ValueError(f"unknown record {kind}")
    if not terminal or model.mmio_reads: raise ValueError("incomplete trace")
    if len(memory)!=len(model.ram): raise ValueError("native RAM snapshot size mismatch")
    if memory!=model.ram:
        index=next(i for i,(a,b) in enumerate(zip(memory,model.ram)) if a!=b)
        raise ValueError(f"native RAM differs at 0x{index:x}: RTL={memory[index]}, reference={model.ram[index]}")
    return commits
