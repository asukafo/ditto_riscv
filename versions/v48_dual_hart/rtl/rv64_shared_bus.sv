// Two masters, one in-flight memory beat. Preserve grant on request stalls and
// keep an atomic owner across all beats, including the gap after its read.
module rv64_shared_bus (
    input wire clk, reset,
    input wire [1:0] req_valid, req_write, req_store_check, bus_lock,
    input wire [127:0] req_addr, req_wdata,
    input wire [3:0] req_size,
    output wire [1:0] req_ready, rsp_valid, snoop_write,
    input wire [1:0] rsp_ready,
    output wire mem_valid,
    input wire mem_ready,
    output wire [63:0] mem_addr, mem_wdata,
    output wire [1:0] mem_size,
    output wire mem_write, mem_store_check,
    input wire mem_rsp_valid, mem_rsp_error,
    output wire mem_rsp_ready,
    output reg [63:3] snoop_addr
);
    reg turn, owner, busy, pending_write;
    reg held, held_owner, locked, lock_owner;
    wire lock_active=locked && bus_lock[lock_owner];
    wire selected=held ? held_owner : lock_active ? lock_owner :
                  req_valid[turn] ? turn : !turn;
    assign mem_valid=!reset && !busy && req_valid[selected];
    assign mem_addr=req_addr[selected*64+:64];
    assign mem_wdata=req_wdata[selected*64+:64];
    assign mem_size=req_size[selected*2+:2];
    assign mem_write=req_write[selected];
    assign mem_store_check=req_store_check[selected];
    assign req_ready[0]=mem_valid && mem_ready && !selected;
    assign req_ready[1]=mem_valid && mem_ready && selected;
    assign rsp_valid[0]=!reset && busy && mem_rsp_valid && !owner;
    assign rsp_valid[1]=!reset && busy && mem_rsp_valid && owner;
    assign mem_rsp_ready=!reset && busy && rsp_ready[owner];
    wire completed_write=mem_rsp_valid && mem_rsp_ready && !mem_rsp_error && pending_write;
    assign snoop_write={completed_write && !owner, completed_write && owner};

    always @(posedge clk) begin
        if (reset) begin
            turn<=0;
            owner<=0;
            busy<=0;
            pending_write<=0;
            snoop_addr<=0;
            held<=0;
            held_owner<=0;
            locked<=0;
            lock_owner<=0;
        end else begin
            if (!lock_active) locked<=0;
            if (mem_valid && !mem_ready) begin
                held<=1;
                held_owner<=selected;
            end
            if (mem_valid && mem_ready) begin
                held<=0;
                owner<=selected;
                turn<=!selected;
                busy<=1;
                pending_write<=mem_write;
                snoop_addr<=mem_addr[63:3];
                if (bus_lock[selected]) begin
                    locked<=1;
                    lock_owner<=selected;
                end
            end
            if (mem_rsp_valid && mem_rsp_ready) busy<=0;
        end
    end
endmodule
