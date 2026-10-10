
 // systolic_array.v -- Parameterized rectangular/square systolic array
`default_nettype none

// Safe row-count macro with fallback
`ifdef ARRAY_ROWS
  `define SA_ARRAY_ROWS `ARRAY_ROWS
`elsif ARRAY_SIZE
  `define SA_ARRAY_ROWS `ARRAY_SIZE
`else
  `define SA_ARRAY_ROWS 4
`endif

// Safe column-count macro with fallback
`ifdef ARRAY_COLS
  `define SA_ARRAY_COLS `ARRAY_COLS
`elsif ARRAY_SIZE
  `define SA_ARRAY_COLS `ARRAY_SIZE
`else
  `define SA_ARRAY_COLS 4
`endif

// Safe data-width macro with fallback
`ifdef DATA_WIDTH
  `define SA_DATA_WIDTH `DATA_WIDTH
`else
  `define SA_DATA_WIDTH 8
`endif

module systolic_array #(
    parameter integer ROWS  = `SA_ARRAY_ROWS,
    parameter integer COLS  = `SA_ARRAY_COLS,
    parameter integer WIDTH = `SA_DATA_WIDTH
) (
    input  wire                         clk,
    input  wire                         rst_n,

    input  wire [ROWS*WIDTH-1:0]        a_edge_in,
    input  wire [COLS*WIDTH-1:0]        b_edge_in,

    output wire [ROWS*COLS*2*WIDTH-1:0] acc_flat
);

    // Internal interconnect wires
    wire [WIDTH-1:0]   a_wire   [0:ROWS-1][0:COLS];
    wire [WIDTH-1:0]   b_wire   [0:ROWS][0:COLS-1];
    wire [2*WIDTH-1:0] acc_wire [0:ROWS-1][0:COLS-1];

    genvar r, c;

    generate
        // Connect A inputs to the left edge of each row
        for (r = 0; r < ROWS; r = r + 1) begin : g_row_edge
            assign a_wire[r][0] =
                a_edge_in[r*WIDTH +: WIDTH];
        end

        // Connect B inputs to the top edge of each column
        for (c = 0; c < COLS; c = c + 1) begin : g_col_edge
            assign b_wire[0][c] =
                b_edge_in[c*WIDTH +: WIDTH];
        end

        // Instantiate ROWS x COLS processing elements
        for (r = 0; r < ROWS; r = r + 1) begin : g_row
            for (c = 0; c < COLS; c = c + 1) begin : g_col

                pe #(
                    .WIDTH(WIDTH)
                ) pe_inst (
                    .clk     (clk),
                    .rst_n   (rst_n),
                    .a_in    (a_wire[r][c]),
                    .b_in    (b_wire[r][c]),
                    .a_out   (a_wire[r][c+1]),
                    .b_out   (b_wire[r+1][c]),
                    .acc_out (acc_wire[r][c])
                );

                // Preserve row-major flattened output ordering
                assign acc_flat[
                    (r*COLS + c)*2*WIDTH +: 2*WIDTH
                ] = acc_wire[r][c];

            end
        end
    endgenerate

endmodule

`default_nettype wire
