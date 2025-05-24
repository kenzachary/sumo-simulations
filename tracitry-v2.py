import traci
import sumolib
import csv
from shapely.geometry import Point, Polygon
import xml.etree.ElementTree as ET

# === CONFIGURATION ===
NET_FILE = "smaller.net.xml"
ROUTE_FILE = "v5_dir_routes.rou.xml"
JUNCTION_ID = "30763114"
OUTPUT_CSV = "junction_times.csv"
SUMMARY_CSV = "junction_summary.csv"
TRIPINFO_FILE = "tripinfo-traci.xml"
STEP_LENGTH = 1.0  # simulation step size in seconds

# === LOAD NETWORK ===
net = sumolib.net.readNet(NET_FILE)
junction = net.getNode(JUNCTION_ID)
junction_polygon = Polygon(junction.getShape())

def is_inside_junction(x, y):
    return junction_polygon.contains(Point(x, y))

# === START SUMO ===
sumoCmd = [
    "sumo",  # Use "sumo-gui" for visualization
    "-n", NET_FILE,
    "-r", ROUTE_FILE,
    "--additional-files", "lane_emissions_output.add.xml",
    "--tripinfo-output", TRIPINFO_FILE
]
traci.start(sumoCmd)

vehicle_times = {}  # Dictionary to track vehicle data
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

# === PARSE TRIPINFO FILE FOR DEPART/ARRIVAL TIMES ===
try:
    tree = ET.parse(TRIPINFO_FILE)
    root = tree.getroot()
    for trip in root.findall("tripinfo"):
        veh_id = trip.attrib["id"]
        if veh_id in vehicle_times:
            vehicle_times[veh_id]['depart'] = float(trip.attrib.get("depart", 0.0))
            vehicle_times[veh_id]['arrival'] = float(trip.attrib.get("arrival", 0.0))
except FileNotFoundError:
    print(f"Warning: tripinfo file not found: {TRIPINFO_FILE}")

# === WRITE PER-VEHICLE CSV ===
with open(OUTPUT_CSV, mode="w", newline="") as csvfile:
    writer = csv.writer(csvfile)
    writer.writerow(["vehicle_id", "vtype", "entry_time_s", "exit_time_s", "depart_time_s", "arrival_time_s"])
    for veh_id, data in vehicle_times.items():
        entry = data.get('enter')
        exit_ = data.get('exit')
        vtype = data.get('vtype', "unknown")
        depart = data.get('depart', "")
        arrival = data.get('arrival', "")
        if entry is not None and exit_ is not None:
            writer.writerow([veh_id, vtype, entry, exit_, depart, arrival])

# === COMPUTE AVERAGE TIME INSIDE JUNCTION ===
durations = [
    data['exit'] - data['enter']
    for data in vehicle_times.values()
    if 'enter' in data and 'exit' in data
]

avg_junction_time = sum(durations) / len(durations) if durations else 0.0
print(f"Average time inside junction ({JUNCTION_ID}): {avg_junction_time:.2f} seconds")

# === COMPUTE AVERAGE TOTAL TRIP TIME FROM TRIPINFO ===
trip_durations = [
    float(trip.attrib.get("duration", 0.0))
    for trip in root.findall("tripinfo")
] if root is not None else []

avg_trip_duration = sum(trip_durations) / len(trip_durations) if trip_durations else 0.0
print(f"Average total trip time: {avg_trip_duration:.2f} seconds")

# === WRITE SUMMARY CSV ===
with open(SUMMARY_CSV, "w", newline="") as summary_file:
    writer = csv.writer(summary_file)
    writer.writerow(["junction_id", "vehicles_in_junction", "avg_time_in_junction_s", "avg_total_trip_time_s"])
    writer.writerow([JUNCTION_ID, len(durations), f"{avg_junction_time:.2f}", f"{avg_trip_duration:.2f}"])
