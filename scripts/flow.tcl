# ==============================================================================
# 1. Read variables from environment with safe defaults
# ==============================================================================
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

# ==============================================================================
# 2. Define Sky130 PDK Paths
# ==============================================================================
set pdk_dir "./conda-env/share/pdk/sky130A"
set tech_lef "${pdk_dir}/libs.ref/sky130_fd_sc_hd/techlef/sky130_fd_sc_hd__nom.tlef"
set std_cell_lef "${pdk_dir}/libs.ref/sky130_fd_sc_hd/lef/sky130_fd_sc_hd.lef"
set lib_file "${pdk_dir}/libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib"
set netlist_verilog "systolic_project/synth/systolic_netlist.v"

# ==============================================================================
# 3. Read Liberty, LEFs, and Netlist
# ==============================================================================
puts "Reading Liberty and LEF files..."
read_liberty $lib_file
read_lef $tech_lef
read_lef $std_cell_lef

puts "Reading synthesized netlist..."
read_verilog $netlist_verilog
link_design "systolic_array"

# ==============================================================================
# 4. Initialize Floorplan & Make Routing Tracks (Fix for 8000+ Pin Out-of-Bounds)
# ==============================================================================
# For extremely high pin counts (8000+ IOs), increase core margin to expand die perimeter
if {$UTIL >= 60} {
    set core_margin 35.0
} elseif {$UTIL >= 40} {
    set core_margin 25.0
} else {
    set core_margin 15.0
}

puts "Initializing floorplan with utilization: ${UTIL}%, site: ${site_name}, margin: ${core_margin}um"
initialize_floorplan \
    -utilization $UTIL \
    -aspect_ratio 1.0 \
    -core_space $core_margin \
    -site $site_name

# Initialize routing grid tracks for pin placement and global routing
make_tracks
# ==============================================================================
# 5. Define Clock & Timing Constraints
# ==============================================================================
create_clock -name clk -period $CLK_PERIOD [get_ports clk]

# Get all inputs except clock
set in_ports [get_ports * -filter "direction == input && name != clk"]
if {[llength $in_ports] > 0} {
    set_input_delay -clock clk 0.2 $in_ports
}

set_output_delay -clock clk 0.2 [all_outputs]

# ==============================================================================
# 6. Global Placement, Pin Placement & Detailed Placement
# ==============================================================================
puts "Running global placement..."
if {$UTIL >= 60} {
    global_placement -density_penalty 0.05
} else {
    global_placement
}

puts "Running pin placement (Multi-layer allocation)..."
# Multi-layer IO pin assignment to avoid PPL-0024 capacity issues
set io_hor_layers [list met3 met5]
set io_ver_layers [list met2 met4]

# Set minimum pin spacing to 1 track
set_io_pin_constraint -pin_spacing 1

# Attempt pin placement with multi-layer assignment
if {[catch {
    place_pins -hor_layers $io_hor_layers \
               -ver_layers $io_ver_layers \
               -random
} err]} {
    puts "\[WARNING\] Standard pin placement failed: $err"
    puts "\[INFO\] Retrying pin placement with annealing fallback..."
    place_pins -hor_layers $io_hor_layers \
               -ver_layers $io_ver_layers \
               -annealing
}

puts "Running detailed placement..."
detailed_placement
check_placement

# ==============================================================================
# 7. Create Output Directory and Save Database
# ==============================================================================
if {[info exists ::env(RUN_TAG)] && $::env(RUN_TAG) != ""} {
    set run_dir "systolic_project/runs/$::env(RUN_TAG)"
} else {
    set run_dir "systolic_project/runs/smoke_test"
}

file mkdir $run_dir
write_db "${run_dir}/final.odb"
puts "Successfully saved database to ${run_dir}/final.odb"
