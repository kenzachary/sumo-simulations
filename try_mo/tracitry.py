import traci
import sumolib
import csv
from shapely.geometry import Point, Polygon

# === CONFIGURATION ===
NET_FILE = "smaller.net.xml"
ROUTE_FILE = "v5_dir_routes.rou.xml"
JUNCTION_ID = "30763114"  # <-- Replace with actual junction ID
OUTPUT_CSV = "junction_times.csv"
STEP_LENGTH = 1.0  # simulation step size in seconds

# === LOAD NETWORK ===
net = sumolib.net.readNet(NET_FILE)
junction = net.getNode(JUNCTION_ID)
junction_polygon = Polygon(junction.getShape())

def is_inside_junction(x, y):
    return junction_polygon.contains(Point(x, y))

# === START SUMO ===
sumoCmd = [
    "sumo",  # Use "sumo-gui" if you want visualization
    "-n", NET_FILE,
    "-r", ROUTE_FILE,
    "--additional-files","lane_emissions_output.add.xml",
    "--tripinfo-output", "tripinfo-traci.xml"
]
traci.start(sumoCmd)

vehicle_times = {}  # Dictionary to track entry/exit times and vehicle type
step = 0

while traci.simulation.getMinExpectedNumber() > 0:
    traci.simulationStep()

    for veh_id in traci.vehicle.getIDList():
        x, y = traci.vehicle.getPosition(veh_id)
        inside = is_inside_junction(x, y)

        if inside:
            if veh_id not in vehicle_times:
                vtype = traci.vehicle.getTypeID(veh_id)
                vehicle_times[veh_id] = {
                    'enter': step * STEP_LENGTH,
                    'vtype': vtype
                }
        elif veh_id in vehicle_times and 'exit' not in vehicle_times[veh_id]:
            vehicle_times[veh_id]['exit'] = step * STEP_LENGTH

    step += 1

traci.close()

# === WRITE TO CSV ===
with open(OUTPUT_CSV, mode="w", newline="") as csvfile:
    writer = csv.writer(csvfile)
    writer.writerow(["vehicle_id", "vtype", "entry_time_s", "exit_time_s"])
    for veh_id, data in vehicle_times.items():
        entry = data.get('enter')
        exit_ = data.get('exit')
        vtype = data.get('vtype', "unknown")
        if entry is not None and exit_ is not None:
            writer.writerow([veh_id, vtype, entry, exit_])
