// M/S/U control state. No H/F/D, PMP entries, debug mode, or optional CSR families.
module rv64_csr # (parameter EXTENSIONS=1) (
    input wire clk,reset,retire,
    input wire [63:0] irq_pending,time_value,
    input wire csr_request,csr_commit,
    input wire [11:0] address, input wire [2:0] command,
    input wire [4:0] source_index, input wire [63:0] source_value,
    output reg [63:0] read_data, output wire illegal,
    input wire mret,sret,wfi,sfence,return_commit,
    output wire system_illegal, output wire [63:0] return_pc,
    input wire trap, input wire [63:0] exception_pc,exception_cause,exception_value,
    output wire [63:0] vector,
    output reg [1:0] privilege,
    output wire [1:0] data_privilege,
    output reg [63:0] satp,
    output wire sum,mxr,
    output reg interrupt_valid, output reg [63:0] interrupt_cause
);
    localparam [63:0] STATUS_MASK=64'h00000000007e19aa, STATUS_FIXED=64'h0000000a00000000;
    localparam [63:0] S_MASK=64'h00000003000c0122;
    reg [63:0] status,medeleg,mideleg,mie,mip_soft,mtvec,mscratch,mepc,mcause,mtval;
    reg [63:0] stvec,sscratch,sepc,scause,stval,mcounteren,scounteren,mcountinhibit,mcycle,minstret;
    reg exists;
    reg [63:0] write_base,write_value;
    wire [63:0] operand=command[2] ? {59'd0,source_index} : source_value;
    wire write_requested=command[1:0]==1 || source_index!=0;
    wire [63:0] pending=mip_soft | (irq_pending & 64'haaa);
    wire counter_denied=(address==12'hc00 || address==12'hc01 || address==12'hc02) && privilege!=3 &&
        (!mcounteren[{4'd0,address[1:0]}] || (privilege==0 && !scounteren[{4'd0,address[1:0]}]));
    assign illegal=csr_request && (!exists || privilege<address[9:8] ||
        (write_requested && address[11:10]==3) || counter_denied || (address==12'h180 && privilege==1 && status[20]));
    assign system_illegal=(mret && privilege!=3) || (sret && (privilege==0 || (privilege==1 && status[22]))) ||
        (sfence && (privilege==0 || (privilege==1 && status[20]))) || (wfi && (privilege==0 || (privilege==1 && status[21])));
    assign return_pc=mret ? mepc : sepc;
    assign data_privilege=privilege==3 && status[17] ? status[12:11] : privilege;
    assign sum=status[18]; assign mxr=status[19];
    wire delegated=privilege!=3 && exception_cause[62:6]==0 &&
        (exception_cause[63] ? mideleg[exception_cause[5:0]] : medeleg[exception_cause[5:0]]);
    wire [63:0] target_vector=delegated ? stvec : mtvec;
    assign vector=(target_vector & ~64'd3)+((exception_cause[63] && target_vector[1:0]==1) ? {56'd0,exception_cause[5:0],2'd0} : 64'd0);
    integer rank;
    reg [5:0] number;
    reg enabled;
    always @* begin
        read_data=0; exists=1;
        case (address)
            12'h100: read_data=status&S_MASK;
            12'h104: read_data=mie&mideleg;
            12'h105: read_data=stvec;
            12'h106: read_data=scounteren;
            12'h140: read_data=sscratch;
            12'h141: read_data=sepc;
            12'h142: read_data=scause;
            12'h143: read_data=stval;
            12'h144: read_data=pending&mideleg;
            12'h180: read_data=satp;
            12'h300: read_data=status;
            12'h301: read_data=EXTENSIONS!=0 ? 64'h8000000000141105 : 64'h8000000000000100;
            12'h302: read_data=medeleg;
            12'h303: read_data=mideleg;
            12'h304: read_data=mie;
            12'h305: read_data=mtvec;
            12'h306: read_data=mcounteren;
            12'h320: read_data=mcountinhibit;
            12'h340: read_data=mscratch;
            12'h341: read_data=mepc;
            12'h342: read_data=mcause;
            12'h343: read_data=mtval;
            12'h344: read_data=pending;
            12'hb00,12'hc00: read_data=mcycle;
            12'hb02,12'hc02: read_data=minstret;
            12'hc01: read_data=time_value;
            12'hf11,12'hf12,12'hf13,12'hf14,12'hf15: read_data=0;
            default: exists=0;
        endcase
        write_base=address==12'h344 ? mip_soft : address==12'h144 ? mip_soft&mideleg : read_data;
        case (command[1:0])
            1: write_value=operand;
            2: write_value=write_base|operand;
            3: write_value=write_base&~operand;
            default: write_value=write_base;
        endcase
        interrupt_valid=0; interrupt_cause=0; number=0; enabled=0;
        // Highest priority is selected first: MEI, MSI, MTI, SEI, SSI, STI.
        for (rank=0;rank<6;rank=rank+1) begin
            case (rank)
                0:number=11; 1:number=3; 2:number=7; 3:number=9; 4:number=1; default:number=5;
            endcase
            enabled=mideleg[number] ? (privilege==0 || (privilege==1 && status[1])) : (privilege<3 || status[3]);
            if (!interrupt_valid && pending[number] && mie[number] && enabled) begin
                interrupt_valid=1; interrupt_cause=64'h8000000000000000|{58'd0,number};
            end
        end
    end
    always @(posedge clk) begin
        if (reset) begin
            privilege<=3; status<=STATUS_FIXED; satp<=0; medeleg<=0; mideleg<=0; mie<=0; mip_soft<=0;
            mtvec<=0; mscratch<=0; mepc<=0; mcause<=0; mtval<=0;
            stvec<=0; sscratch<=0; sepc<=0; scause<=0; stval<=0;
            mcounteren<=0; scounteren<=0; mcountinhibit<=0; mcycle<=0; minstret<=0;
        end else begin
            if (!mcountinhibit[0]) mcycle<=mcycle+1;
            if (retire && !mcountinhibit[2]) minstret<=minstret+1;
            if (csr_commit && write_requested && !illegal) case (address)
                12'h100: status<=(status&~64'hc0122)|(write_value&64'hc0122)|STATUS_FIXED;
                12'h104: mie<=(mie&~mideleg)|(write_value&mideleg);
                12'h105: stvec<=(write_value&~64'd3)|(write_value[1:0]==1 ? 64'd1 : 64'd0);
                12'h106: scounteren<=write_value&7;
                12'h140: sscratch<=write_value;
                12'h141: sepc<=write_value&(EXTENSIONS!=0 ? ~64'd1 : ~64'd3);
                12'h142: scause<=write_value;
                12'h143: stval<=write_value;
                12'h144: mip_soft<=(mip_soft&~(mideleg&64'd2))|(write_value&mideleg&64'd2);
                12'h180: if (write_value[63:60]==0 || write_value[63:60]==8) satp<={write_value[63:60],16'd0,write_value[43:0]};
                12'h300: begin
                    status<=(write_value&STATUS_MASK)|STATUS_FIXED;
                    if (write_value[12:11]==2) status[12:11]<=0;
                end
                12'h302: medeleg<=write_value&64'hb3ff;
                12'h303: mideleg<=write_value&64'h222;
                12'h304: mie<=write_value&64'haaa;
                12'h305: mtvec<=(write_value&~64'd3)|(write_value[1:0]==1 ? 64'd1 : 64'd0);
                12'h306: mcounteren<=write_value&7;
                12'h320: mcountinhibit<=write_value&5;
                12'h340: mscratch<=write_value;
                12'h341: mepc<=write_value&(EXTENSIONS!=0 ? ~64'd1 : ~64'd3);
                12'h342: mcause<=write_value;
                12'h343: mtval<=write_value;
                12'h344: mip_soft<=write_value&64'h222;
                12'hb00: mcycle<=write_value;
                12'hb02: minstret<=write_value;
                default: ;
            endcase
            if (return_commit && !system_illegal) begin
                if (mret) begin
                    privilege<=status[12:11]; status[3]<=status[7]; status[7]<=1; status[12:11]<=0;
                    if (status[12:11]!=3) status[17]<=0;
                end else begin
                    privilege<=status[8] ? 2'd1 : 2'd0; status[1]<=status[5]; status[5]<=1; status[8]<=0; status[17]<=0;
                end
            end
            if (trap) begin
                if (delegated) begin
                    sepc<=exception_pc&~64'd1; scause<=exception_cause; stval<=exception_value;
                    status[5]<=status[1]; status[1]<=0; status[8]<=privilege==1; privilege<=1;
                end else begin
                    mepc<=exception_pc&(EXTENSIONS!=0 ? ~64'd1 : ~64'd3); mcause<=exception_cause; mtval<=exception_value;
                    status[7]<=status[3]; status[3]<=0; status[12:11]<=privilege; privilege<=3;
                end
            end
        end
    end
endmodule
