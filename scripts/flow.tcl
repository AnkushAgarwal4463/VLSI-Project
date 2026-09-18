# ==============================================================================
# 1. Load PDK Technology LEF, Macro LEF, and Liberty Files
# ==============================================================================
read_lef pdk/Nangate45/NangateOpenCellLibrary.tech.lef
read_lef pdk/Nangate45/NangateOpenCellLibrary.macro.mod.lef
read_liberty pdk/Nangate45/NangateOpenCellLibrary_typical.lib

# ==============================================================================
# 2. Read Structural Netlist and Initialize Design
# ==============================================================================
read_verilog systolic_project/synth/systolic_netlist.v
link_design systolic_array

# Read SDC constraints for timing setup
read_sdc constraints.sdc

# ==============================================================================
# 3. Floorplanning & Power Grid Generation
# ==============================================================================
# Initialize die area with 50% utilization, 10um margin around core
initialize_floorplan -utilization 50 -aspect_ratio 1.0 -core_space 10

# Place primary I/O pins automatically around perimeter
place_pins -hor_layers metal3 -ver_layers metal2

# Generate Power/Ground stripes (VDD / VSS)
make_tracks
add_global_connection -net VDD -inst_pattern .* -pin_pattern VDD -power
add_global_connection -net VSS -inst_pattern .* -pin_pattern VSS -ground

# ==============================================================================
# 4. Placement Stage
# ==============================================================================
# Insert well-taps and end-caps to prevent latch-up
tapcell -endcap_master TAPCELL_X1 -distance 14

# Global placement (place standard cells roughly)
global_placement

# Detailed placement (legalize cell positions)
detailed_placement

# ==============================================================================
# 5. Clock Tree Synthesis (CTS)
# ==============================================================================
# Build clock tree buffers for low skew
configure_cts -buf_list {BUF_X1 BUF_X2 BUF_X4}
clock_tree_synthesis

# Re-legalize placement after CTS buffer insertion
detailed_placement

# ==============================================================================
# 6. Routing Stage
# ==============================================================================
# Global routing (estimate wire tracks)
global_route

# Detailed routing using TritonRoute
detailed_route

# Insert filler cells to fill empty core spaces
filler_placement -filler_masters {FILLCELL_X1 FILLCELL_X2 FILLCELL_X4 FILLCELL_X8}

# ==============================================================================
# 7. Final STA & Export Output Artifacts
# ==============================================================================
# Check for setup/hold timing violations
report_checks -path_delay min_max -fields {slew cap input fanout} -digits 3

# Report total chip power breakdown
report_power

# Export layout (DEF) and routed netlist
write_def systolic_project/pnr/systolic_array.def
write_verilog systolic_project/pnr/systolic_array_pnr.v

puts "=== OpenROAD Flow Completed Successfully ==="
exit
