// RV64C integer instructions. Floating-point compressed encodings remain illegal.
module rv64_decompress (
    input wire [15:0] c,
    output reg [31:0] instruction,
    output reg illegal
);
    wire [4:0] rd=c[11:7], rs2=c[6:2];
    wire [4:0] prime1={2'b01,c[9:7]}, prime2={2'b01,c[4:2]};
    wire [11:0] signed_imm={{6{c[12]}},c[12],c[6:2]};
    reg [11:0] offset;
    reg [8:0] branch_offset;
    function [31:0] itype;
        input [6:0] opcode; input [4:0] dest,source; input [2:0] fun; input [11:0] imm;
        begin itype={imm,source,fun,dest,opcode}; end
    endfunction
    function [31:0] rtype;
        input [6:0] opcode,fun7; input [4:0] dest,s1,s2; input [2:0] fun;
        begin rtype={fun7,s2,s1,fun,dest,opcode}; end
    endfunction
    function [31:0] store;
        input [4:0] s1,s2; input [2:0] fun; input [11:0] imm;
        begin store={imm[11:5],s2,s1,fun,imm[4:0],7'h23}; end
    endfunction
    function [31:0] jump;
        input [11:0] imm;
        reg [20:1] full_imm;
        reg unused_alignment;
        begin unused_alignment=imm[0]; full_imm={{9{imm[11]}},imm[11:1]}; jump={full_imm[20],full_imm[10:1],full_imm[11],full_imm[19:12],5'd0,7'h6f}; end
    endfunction
    function [31:0] branch;
        input [4:0] source; input different; input [8:0] imm;
        reg [12:1] full_imm;
        reg unused_alignment;
        begin
            unused_alignment=imm[0]; full_imm={{4{imm[8]}},imm[8:1]};
            branch={full_imm[12],full_imm[10:5],5'd0,source,2'd0,different,full_imm[4:1],full_imm[11],7'h63};
        end
    endfunction
    always @* begin
        instruction=32'h00000013; illegal=0; offset=0; branch_offset=0;
        case (c[1:0])
            0: case (c[15:13])
                0: begin
                    offset={2'd0,c[10:7],c[12:11],c[5],c[6],2'd0};
                    illegal=offset==0; instruction=itype(7'h13,prime2,5'd2,0,offset);
                end
                2,3: begin
                    offset=c[13] ? {4'd0,c[6:5],c[12:10],3'd0} : {5'd0,c[5],c[12:10],c[6],2'd0};
                    instruction=itype(7'h03,prime2,prime1,c[13] ? 3'd3 : 3'd2,offset);
                end
                6,7: begin
                    offset=c[13] ? {4'd0,c[6:5],c[12:10],3'd0} : {5'd0,c[5],c[12:10],c[6],2'd0};
                    instruction=store(prime1,prime2,c[13] ? 3'd3 : 3'd2,offset);
                end
                default: illegal=1;
            endcase
            1: case (c[15:13])
                0: instruction=itype(7'h13,rd,rd,0,signed_imm);
                1: begin illegal=rd==0; instruction=itype(7'h1b,rd,rd,0,signed_imm); end
                2: instruction=itype(7'h13,rd,0,0,signed_imm);
                3: begin
                    if (rd==2) begin
                        offset={{2{c[12]}},c[12],c[4:3],c[5],c[2],c[6],4'd0};
                        illegal=offset==0; instruction=itype(7'h13,2,2,0,offset);
                    end else begin
                        illegal=signed_imm==0;
                        instruction={{14{c[12]}},c[12],c[6:2],rd,7'h37};
                    end
                end
                4: case (c[11:10])
                    0: instruction=itype(7'h13,prime1,prime1,5,{6'd0,c[12],c[6:2]});
                    1: instruction=itype(7'h13,prime1,prime1,5,{6'b010000,c[12],c[6:2]});
                    2: instruction=itype(7'h13,prime1,prime1,7,signed_imm);
                    3: begin
                        if (!c[12]) case (c[6:5])
                            0: instruction=rtype(7'h33,7'h20,prime1,prime1,prime2,0);
                            1: instruction=rtype(7'h33,0,prime1,prime1,prime2,4);
                            2: instruction=rtype(7'h33,0,prime1,prime1,prime2,6);
                            3: instruction=rtype(7'h33,0,prime1,prime1,prime2,7);
                        endcase
                        else case (c[6:5])
                            0: instruction=rtype(7'h3b,7'h20,prime1,prime1,prime2,0);
                            1: instruction=rtype(7'h3b,0,prime1,prime1,prime2,0);
                            default: illegal=1;
                        endcase
                    end
                endcase
                5: begin
                    offset={c[12],c[8],c[10:9],c[6],c[7],c[2],c[11],c[5:3],1'b0};
                    instruction=jump(offset);
                end
                6,7: begin
                    branch_offset={c[12],c[6:5],c[2],c[11:10],c[4:3],1'b0};
                    instruction=branch(prime1,c[13],branch_offset);
                end
                default: illegal=1;
            endcase
            2: case (c[15:13])
                0: instruction=itype(7'h13,rd,rd,1,{6'd0,c[12],c[6:2]});
                2,3: begin
                    illegal=rd==0;
                    offset=c[13] ? {3'd0,c[4:2],c[12],c[6:5],3'd0} : {4'd0,c[3:2],c[12],c[6:4],2'd0};
                    instruction=itype(7'h03,rd,2,c[13] ? 3'd3 : 3'd2,offset);
                end
                4: begin
                    if (rs2!=0) instruction=rtype(7'h33,0,rd,c[12] ? rd : 5'd0,rs2,0);
                    else if (rd!=0) instruction=itype(7'h67,c[12] ? 5'd1 : 5'd0,rd,0,0);
                    else if (c[12]) instruction=32'h00100073;
                    else illegal=1;
                end
                6,7: begin
                    offset=c[13] ? {3'd0,c[9:7],c[12:10],3'd0} : {4'd0,c[8:7],c[12:9],2'd0};
                    instruction=store(2,rs2,c[13] ? 3'd3 : 3'd2,offset);
                end
                default: illegal=1;
            endcase
            default: illegal=1;
        endcase
    end
endmodule
