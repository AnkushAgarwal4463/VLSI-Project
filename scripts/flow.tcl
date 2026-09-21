# Read variables from environment with safe defaults
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

# Set site name from environment, defaulting to Sky130 site (or FreePDK45 if specified)
if {[info exists ::env(SITE)] && $::env(SITE) != ""} {
    set site_name $::env(SITE)
} else {
    set site_name "unithd"
}

puts "Initializing floorplan with utilization: ${UTIL}%, site: ${site_name}"

initialize_floorplan \
    -utilization $UTIL \
    -aspect_ratio 1.0 \
    -core_space 10.0 \
    -site $site_name

set_input_delay -clock clk 0.2 [all_inputs]
set_output_delay -clock clk 0.2 [all_outputs]
