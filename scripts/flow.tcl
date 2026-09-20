# OpenROAD Place & Route Flow Script

# 1. Read Technology and Cell LEFs
read_lef $::env(TECH_LEF_FILE)
read_lef $::env(CELL_LEF_FILE)

# 2. Read Liberty File & Synthesized Netlist
read_liberty $::env(LIB_FILE)
read_verilog systolic_project/synth/systolic_netlist.v
link_design systolic_array

# 3. Read Dynamic Timing Constraints (SDC)
read_sdc $::env(SDC_FILE)

# 4. Floorplan Initialization
initialize_floorplan -utilization $::env(UTIL) -aspect_ratio 1.0 -core_space 10.0

# 5. IO Pin Placement
place_pins -hor_layers metal3 -ver_layers metal2

# 6. Global Placement
global_placement

# Finish process
exit
