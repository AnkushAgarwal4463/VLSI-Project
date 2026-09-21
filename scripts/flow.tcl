# 1. Read variables from environment with safe defaults
if {[info exists ::env(UTIL)] && $::env(UTIL) != ""} {
    set UTIL $::env(UTIL)
} else {
    set UTIL 50
}

if {[info exists ::env(CLK_PERIOD)] && $::env(CLK_PERIOD) != ""} {
    set CLK_PERIOD $::env(CLK_PERIOD)
} else {
    set CLK_PERIOD 10.0
}

if {[info exists ::env(SITE)] && $::env(SITE) != ""} {
    set site_name $::env(SITE)
} else {
    set site_name "unithd"
}

# 2. Define Sky130 PDK Paths (installed via Conda/Micromamba)
set pdk_dir "./conda-env/share/pdk/sky130A"
set tech_lef "${pdk_dir}/libs.ref/sky130_fd_sc_hd/techlef/sky130_fd_sc_hd__nom.tlef"
set std_cell_lef "${pdk_dir}/libs.ref/sky130_fd_sc_hd/lef/sky130_fd_sc_hd.lef"
set netlist_verilog "systolic_project/synth/systolic_netlist.v"

# 3. Read Technology & Standard Cell LEFs
puts "Reading LEF files..."
read_lef $tech_lef
read_lef $std_cell_lef

# 4. Read Synthesized Verilog Netlist & Link Top Module
puts "Reading synthesized netlist..."
read_verilog $netlist_verilog
link_design "systolic_array"

# 5. Initialize Floorplan
puts "Initializing floorplan with utilization: ${UTIL}%, site: ${site_name}"

initialize_floorplan \
    -utilization $UTIL \
    -aspect_ratio 1.0 \
    -core_space 10.0 \
    -site $site_name

set_input_delay -clock clk 0.2 [all_inputs]
set_output_delay -clock clk 0.2 [all_outputs]
