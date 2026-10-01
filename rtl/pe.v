// pe.v -- Single Systolic Processing Element (Multiply-Accumulate)
`default_nettype none

// Safe macro definitions with fallbacks
`ifdef DATA_WIDTH
  `define PE_DATA_WIDTH `DATA_WIDTH
`else
  `define PE_DATA_WIDTH 8
`endif

module pe #(
    parameter WIDTH = `PE_DATA_WIDTH
) (
    input  wire                 clk,
    input  wire                 rst_n,
    input  wire  [WIDTH-1:0]    a_in,
    input  wire  [WIDTH-1:0]    b_in,
    output logic [WIDTH-1:0]    a_out,
    output logic [WIDTH-1:0]    b_out,
    output logic [2*WIDTH-1:0]  acc_out
);

    // Explicit combinational multiply intermediate to assist Yosys logic mapping
    logic [2*WIDTH-1:0] mult_prod;

    always_comb begin
        mult_prod = a_in * b_in;
    end

    // Synchronous Pipeline & Accumulation Logic
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            a_out   <= '0;
            b_out   <= '0;
            acc_out <= '0;
        end else begin
            a_out   <= a_in;
            b_out   <= b_in;
            acc_out <= acc_out + mult_prod;
        end
    end

endmodule

`default_nettype wire
