// Four requesters, round-robin arbitration, one downstream adapter transaction.
// A selected client is accepted into holding registers even if downstream stalls.
// Ownership lasts through the response, including both phases of an AMO in the adapter.
module rv64_physical_arbiter #(parameter ONEHOT=0) (
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
    wire found;
    wire [1:0] selected;
    assign busy=state!=IDLE;
    assign u_valid=!reset && (state==REQUEST || (state==IDLE && found));
    generate if (ONEHOT!=0) begin: parallel_grant
        // Each priority order is static. Only the current round-robin turn
        // can contribute a grant, so the payload mux uses one-hot selects.
        wire [3:0] orders [0:3];
        for (genvar first=0;first<4;first=first+1) begin: priority_order
            for (genvar rank=0;rank<4;rank=rank+1) begin: requester
                localparam LANE=(first+rank)%4;
                wire [3:0] earlier;
                for (genvar prev=0;prev<4;prev=prev+1) begin: prefix
                    assign earlier[prev]=prev<rank ? c_valid[(first+prev)%4] : 1'b0;
                end
                assign orders[first][LANE]=turn==2'(first) && c_valid[LANE] && !(|earlier);
            end
        end
        wire [3:0] grant=orders[0]|orders[1]|orders[2]|orders[3];
        assign found=|grant;
        assign selected={grant[2]|grant[3],grant[1]|grant[3]};
        assign c_ready=!reset && state==IDLE ? grant : 4'd0;
        reg [63:0] selected_addr,selected_data;
        reg [1:0] selected_size;
        reg [4:0] selected_amo;
        always @* begin
            selected_addr=0; selected_data=0; selected_size=0; selected_amo=0;
            for(integer lane=0;lane<4;lane=lane+1) begin
                selected_addr=selected_addr | ({64{grant[lane]}} & c_addr[lane*64+:64]);
                selected_data=selected_data | ({64{grant[lane]}} & c_data[lane*64+:64]);
                selected_size=selected_size | ({2{grant[lane]}} & c_size[lane*2+:2]);
                selected_amo=selected_amo | ({5{grant[lane]}} & c_amo[lane*5+:5]);
            end
        end
        assign u_addr=state==IDLE ? selected_addr : address;
        assign u_data=state==IDLE ? selected_data : data;
        assign u_size=state==IDLE ? selected_size : size;
        assign u_write=state==IDLE ? |(grant & c_write) : write_access;
        assign u_atomic=state==IDLE ? |(grant & c_atomic) : atomic_access;
        assign u_amo=state==IDLE ? selected_amo : amo;
    end else begin: indexed_grant
        reg old_found;
        reg [1:0] old_selected,candidate;
        always @* begin
            old_found=0;old_selected=turn;candidate=0;
            for(integer step=0;step<4;step=step+1) begin
                candidate=turn+2'(step);
                if(!old_found && c_valid[candidate]) begin old_selected=candidate;old_found=1;end
            end
        end
        assign c_ready=!reset && state==IDLE && old_found ? (4'b1<<old_selected) : 4'b0;
        assign u_addr=state==IDLE ? c_addr[old_selected*64+:64] : address;
        assign u_data=state==IDLE ? c_data[old_selected*64+:64] : data;
        assign u_size=state==IDLE ? c_size[old_selected*2+:2] : size;
        assign u_write=state==IDLE ? c_write[old_selected] : write_access;
        assign u_atomic=state==IDLE ? c_atomic[old_selected] : atomic_access;
        assign u_amo=state==IDLE ? c_amo[old_selected*5+:5] : amo;
        assign found=old_found;
        assign selected=old_selected;
    end endgenerate
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
