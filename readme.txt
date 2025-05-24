

this is assuming that the receptor point is the center of the intersection
https://chatgpt.com/share/6829e628-4cdc-800b-90f7-0d39ae59698f


Step 1: python first.py
Step 2:duarouter -n for_sd/a_smaller.net.xml --route-files for_sd/sd_trips.trips.xml -o for_sd/sd_dir_routes.rou.xml --additional-files for_sd/sd_vtypes-1.add.xml
Step 3: sumo -n for_sd/a_smaller.net.xml -r for_sd/sd_dir_routes.rou.xml --additional-files for_sd/sd_lane_emissions_output.add.xml --tripinfo-output for_sd/sd_tripinfo.xml
Step 4: python disper_v2.py


open disper_v2.py and change
receptor = np.array([0, 0])  # Center of intersection