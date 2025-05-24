import xml.etree.ElementTree as ET
import csv
from collections import defaultdict

# === FILE PATHS ===
TRIPINFO_XML = "tripinfo-v4.xml"
ROUTES_XML = "v5_dir_routes.rou.xml"
NET_XML = "smaller.net.xml"
OUTPUT_CSV = "non-final-emissions_per_edge.csv"

# === EMISSION FACTORS (g/veh-km) ===
EFs = {
    "car":        {"NOx": 2.7, "CO2": 0, "CO": 49.5,  "PM10": 0.1,  "PM25": 0.1,  "SOx": 0.011},
    "motorcycle": {"NOx": 0.2, "CO2": 0,  "CO": 26,  "PM10": 2.0, "PM25": 2.0, "SOx": 0.004},
    "truck":      {"NOx": 12.5, "CO2": 0, "CO": 12.4,  "PM10": 1.5,  "PM25": 1.5,  "SOx": 0.374},
    "bus":        {"NOx": 12.5, "CO2": 0, "CO": 12.4,  "PM10": 1.5,  "PM25": 1.5,  "SOx": 0.374}
}

# === 1. LOAD EDGE LENGTHS FROM net.xml ===
edge_lengths = {}
net_tree = ET.parse(NET_XML)
for edge in net_tree.findall(".//edge"):
    edge_id = edge.get("id")
    if edge_id.startswith(":"):
        continue  # skip internal junction edges
    for lane in edge.findall("lane"):
        length = float(lane.get("length", 0))
        edge_lengths[edge_id] = length
        break  # one lane's length is enough per edge

# === 2. LOAD VEHICLE ROUTES FROM .rou.xml ===
vehicle_routes = {}
route_tree = ET.parse(ROUTES_XML)
for vehicle in route_tree.findall("vehicle"):
    veh_id = vehicle.get("id")
    route_elem = vehicle.find("route")
    if route_elem is not None:
        # Get the edges from the route element
        # Note: This assumes the route is stored in a single string
        edges = route_elem.get("edges", "").split()
        vehicle_routes[veh_id] = edges
    else:
        print(f"[WARN] No route found for vehicle {veh_id}")

# === 3. LOAD tripinfo.xml AND COMPUTE EMISSIONS ===
edge_hour_emissions = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))  # edge → hour → pollutant → μg
edge_hour_denominator = defaultdict(lambda: defaultdict(float))  # edge → hour → m·s

trip_tree = ET.parse(TRIPINFO_XML)
for trip in trip_tree.findall("tripinfo"):
    veh_id = trip.get("id")
    vType = trip.get("vType")

    if veh_id not in vehicle_routes or vType not in EFs:
        print(f"[WARN] Vehicle {veh_id} not found in routes or emission factors")
        continue
    
    try:
        route_length_tripinfo = float(trip.get("routeLength"))
        route_edges = vehicle_routes[veh_id]
        route_length_sum = sum(edge_lengths.get(e, 0) for e in route_edges)

        if abs(route_length_tripinfo - route_length_sum) > 1.0:
            print(f"[Warning] Vehicle {veh_id}: tripinfo = {route_length_tripinfo:.2f} m, sum(edges) = {route_length_sum:.2f} m")
    except:
        print(f"[ERROR] Error parsing route length for vehicle {veh_id}")
        continue
    try:
        depart = float(trip.get("depart"))
        duration = float(trip.get("duration"))
        route_length = float(trip.get("routeLength"))
        if duration == 0 or route_length == 0:
            print(f"[ERROR] Zero duration or route length for vehicle {veh_id}")
            continue
    except:
        continue

    hour = int(depart // 3600)
    edges = vehicle_routes[veh_id]
    for edge in edges:
        if edge not in edge_lengths:
            print(f"[WARN] Edge {edge} not found in edge lengths")
            continue
        elen = edge_lengths[edge]
        frac = elen / route_length
        print(f"[INFO] Edge {edge} fraction: {frac:.2f}")
        edge_time = duration * frac
        denom = elen * edge_time  # for μg/(m·s)

        edge_hour_denominator[edge][hour] += denom

        for pollutant, ef in EFs[vType].items():
            trip_emission_g = (route_length / 1000) * ef 
            edge_emission_ug = (trip_emission_g * frac) * 1e6
            edge_hour_emissions[edge][hour][pollutant] += edge_emission_ug


# === 4. WRITE OUTPUT (PIVOTED BY HOUR) ===
HOURS = list(range(24))
POLLUTANTS = ["NOx","NO", "NO2", "CO", "CO2", "SOx", "Ozone", "PM10", "PM2.5"]

# Collect emissions in μg/(m·s) per edge → pollutant → hour
pivot_data = defaultdict(lambda: defaultdict(lambda: {hour: 0.0 for hour in HOURS}))

for edge in edge_hour_emissions:
    for hour in HOURS:
        denom = edge_hour_denominator[edge].get(hour, 0)
        data = edge_hour_emissions[edge].get(hour, {})

        NOx = data.get("NOx", 0)
        NO = 0.75 * NOx / denom if denom else 0
        NO2 = 0.25 * NOx / denom if denom else 0

        pivot_data[edge]["NOx"][hour] = round(data.get("NOx", 0) / denom if denom else 0, 6)
        pivot_data[edge]["NO"][hour] = round(NO, 6)
        pivot_data[edge]["NO2"][hour] = round(NO2, 6)
        pivot_data[edge]["CO"][hour] = round(data.get("CO", 0) / denom if denom else 0, 6)
        pivot_data[edge]["CO2"][hour] = round(data.get("CO2", 0) / denom if denom else 0, 6)
        pivot_data[edge]["SOx"][hour] = round(data.get("SOx", 0) / denom if denom else 0, 6)
        pivot_data[edge]["PM10"][hour] = round(data.get("PM10", 0) / denom if denom else 0, 6)
        pivot_data[edge]["PM2.5"][hour] = round(data.get("PM25", 0) / denom if denom else 0, 6)
        pivot_data[edge]["Ozone"][hour] = 0.0  # Placeholder

# Write to CSV
with open(OUTPUT_CSV, "w", newline="") as csvfile:
    writer = csv.writer(csvfile)
    header = ["Edge", "Pollutant"] + [f"{h}-{h+1}" for h in HOURS]
    writer.writerow(header)

    for edge in sorted(pivot_data):
        for pollutant in POLLUTANTS:
            row = [edge, pollutant] + [pivot_data[edge][pollutant][h] for h in HOURS]
            writer.writerow(row)

print(f"[DONE] Wrote {OUTPUT_CSV} in pivoted format by hour")


print(f"[DONE] Wrote {OUTPUT_CSV}")
print(f"[INFO] Emissions per edge/hour in μg/(m·s) written to {OUTPUT_CSV}")

