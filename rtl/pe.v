// pe.v -- Single Systolic Processing Element (Multiply-Accumulate)
`default_nettype none

// Safe macro definitions with fallbacks
`ifdef DATA_WIDTH
  `define PE_DATA_WIDTH `DATA_WIDTH
`else
  `define PE_DATA_WIDTH 8
`endif

module pe #(
    parameter integer WIDTH = `PE_DATA_WIDTH
) (
    input  wire                 clk,
    input  wire                 rst_n,
    input  wire [WIDTH-1:0]     a_in,
    input  wire [WIDTH-1:0]     b_in,
    output reg  [WIDTH-1:0]     a_out,
    output reg  [WIDTH-1:0]     b_out,
    output reg  [(2*WIDTH)-1:0] acc_out
);

    // Guard parameter against underflow during expression evaluation
    localparam integer ACC_WIDTH = (WIDTH > 0) ? (2 * WIDTH) : 2;

    // Intermediate multiplication wire
    wire [ACC_WIDTH-1:0] mult_prod;

    assign mult_prod = $unsigned(a_in) * $unsigned(b_in);

    // Synchronous Pipeline & Accumulation Logic
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            a_out   <= {WIDTH{1'b0}};
            b_out   <= {WIDTH{1'b0}};
            acc_out <= {ACC_WIDTH{1'b0}};
        end else begin
            a_out   <= a_in;
            b_out   <= b_in;
            acc_out <= acc_out + mult_prod;
        end
    end

endmodule

`default_nettype wire
