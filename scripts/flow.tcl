# Set site name from environment, defaulting to FreePDK45 verified site
if {[info exists ::env(SITE)] && $::env(SITE) != ""} {
    set site_name $::env(SITE)
} else {
    set site_name "FreePDK45_38x28_10R_NP_162NW_34O"
}

puts "Initializing floorplan with utilization: ${UTIL}%, site: ${site_name}"

initialize_floorplan \
    -utilization $UTIL \
    -aspect_ratio 1.0 \
    -core_space 10.0 \
    -site $site_name

set_input_delay -clock clk 0.2 [all_inputs]
set_output_delay -clock clk 0.2 [all_outputs]
