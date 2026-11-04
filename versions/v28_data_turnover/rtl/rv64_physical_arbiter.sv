// Four requesters, round-robin arbitration, one downstream adapter transaction.
// A selected client is accepted into holding registers even if downstream stalls.
// Ownership lasts through the response, including both phases of an AMO in the adapter.
module rv64_physical_arbiter (
    input wire clk,reset,
    input wire [3:0] c_valid,output wire [3:0] c_ready,
    input wire [255:0] c_addr,c_data,input wire [7:0] c_size,
    input wire [3:0] c_write,c_atomic,input wire [19:0] c_amo,
    output wire [3:0] c_rsp_valid,input wire [3:0] c_rsp_ready,
    output wire u_valid,input wire u_ready,output wire [63:0] u_addr,u_data,
    output wire [1:0] u_size,output wire u_write,u_atomic,output wire [4:0] u_amo,
    input wire u_rsp_valid,output wire u_rsp_ready,output wire busy,
    output wire data_blocked_by_fetch,fetch_blocked_by_data
);
    localparam [1:0] IDLE=0,REQUEST=1,RESPONSE=2;
    reg [1:0] state,owner,turn;
    reg [63:0] address,data;
    reg [1:0] size;
    reg write_access,atomic_access;
    reg [4:0] amo;
    reg found;
    reg [1:0] selected,candidate;
    always @* begin
        found=0;selected=turn;candidate=0;
        for(integer step=0;step<4;step=step+1) begin
            candidate=turn+2'(step);
            if(!found && c_valid[candidate]) begin selected=candidate;found=1;end
        end
    end
    assign busy=state!=IDLE;
    assign c_ready=!reset && state==IDLE && found ? (4'b1<<selected) : 4'b0;
    assign u_valid=!reset && (state==REQUEST || (state==IDLE && found));
    assign u_addr=state==IDLE ? c_addr[selected*64+:64] : address;
    assign u_data=state==IDLE ? c_data[selected*64+:64] : data;
    assign u_size=state==IDLE ? c_size[selected*2+:2] : size;
    assign u_write=state==IDLE ? c_write[selected] : write_access;
    assign u_atomic=state==IDLE ? c_atomic[selected] : atomic_access;
    assign u_amo=state==IDLE ? c_amo[selected*5+:5] : amo;
    assign c_rsp_valid=state==RESPONSE && u_rsp_valid ? (4'b1<<owner) : 4'b0;
    assign u_rsp_ready=state==RESPONSE && c_rsp_ready[owner];
    // Lanes 0/2 belong to instruction cache/walker, lanes 1/3 to data cache/walker.
    assign data_blocked_by_fetch=(c_valid[1] || c_valid[3]) && state!=IDLE && !owner[0];
    assign fetch_blocked_by_data=(c_valid[0] || c_valid[2]) && state!=IDLE && owner[0];
    always @(posedge clk) begin
        if(reset) begin state<=IDLE;owner<=0;turn<=0;address<=0;data<=0;size<=0;write_access<=0;atomic_access<=0;amo<=0;end
        else case(state)
            IDLE: if(found) begin
                owner<=selected;address<=u_addr;data<=u_data;size<=u_size;
                write_access<=u_write;atomic_access<=u_atomic;amo<=u_amo;
                state<=u_ready ? RESPONSE : REQUEST;
            end
            REQUEST: if(u_ready) state<=RESPONSE;
            RESPONSE: if(u_rsp_valid && u_rsp_ready) begin state<=IDLE;turn<=owner+1'b1;end
            default:state<=IDLE;
        endcase
    end
endmodule
