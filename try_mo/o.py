import csv
from datetime import datetime, timedelta
from xml.etree.ElementTree import Element, SubElement, ElementTree
import xml.etree.ElementTree as ET
import random

PH_TZ_OFFSET = timedelta(hours=8)

# === CONFIGURATION ===
INPUT_CSV = "traffic_flow_may_17.csv"
OUTPUT_TRIPS = "v5_trips.trips.xml"
VTYPES_XML = "vtypes-1.add.xml"
NET_XML = "smaller.net.xml"
VEHICLE_WHITELIST = {"car", "motorcycle", "truck", "bus"}

# Map directions to actual edge IDs in your SUMO network
DIRECTION_TO_EDGE_IN = {
    "north": "237386421",
    "east": "-29251749#0",
    "south": "-617654357#1",
    "west": "4922743#4"
}

DIRECTION_TO_EDGE_OUT = {
    "north": "-1232571604",
    "east": "29251749#0",
    "south": "617654357#1",
    "west": "-4922743#4"
}

# === Load vehicle types and speeds ===
def load_speeds_from_vtypes(vtypes_file):
    tree = ET.parse(vtypes_file)
    root = tree.getroot()
    speed_map = {}
    for vtype in root.iter("vType"):
        vtype_id = vtype.attrib["id"]
        speed = float(vtype.attrib.get("maxSpeed", vtype.attrib.get("speed", "13.89")))
        speed_map[vtype_id] = speed
    return speed_map

SPEED_LOOKUP = load_speeds_from_vtypes(VTYPES_XML)

# === Load edge lengths ===
def load_edge_lengths(net_file):
    edge_map = {}
    tree = ET.parse(net_file)
    for edge in tree.findall("edge"):
        if "function" in edge.attrib and edge.attrib["function"] == "internal":
            continue
        for lane in edge.findall("lane"):
            edge_id = edge.attrib["id"]
            length = float(lane.attrib["length"])
            edge_map[edge_id] = length
    return edge_map

EDGE_LENGTHS = load_edge_lengths(NET_XML)

# === Helpers ===
def estimate_depart(junction_time, from_edge, vtype):
    length = EDGE_LENGTHS.get(from_edge, 100)
    speed = SPEED_LOOKUP.get(vtype, 13.89)
    travel_time = length / speed
    return round(junction_time - travel_time)

def parse_iso_with_nanos(iso_str):
    # Supports ISO format with or without fractional seconds, strips trailing 'Z'
    if '.' in iso_str:
        base, frac = iso_str.split('.')
        frac = frac.rstrip('Z')
        frac = (frac + "000000")[:6]  # microseconds padded or truncated to 6 digits
        iso_str = f"{base}.{frac}Z"
    return datetime.strptime(iso_str, "%Y-%m-%dT%H:%M:%S.%fZ")

# === STEP 1: Read CSV and detect header ===
print("[INFO] Reading CSV with directional fields...")
parsed_rows = []

with open(INPUT_CSV, newline='') as f:
    lines = f.readlines()

header_index = -1
required_headers = [
    "direction_entry",
    "direction_exit",
    "entered_time",
    "exit_time",
    "vehicle_id",
    "vehicle_type_entry",
    "vehicle_type_exit"
]

for i, line in enumerate(lines):
    if all(h in line for h in required_headers):
        print(f"[INFO] Header found at line {i}: {line.strip()}")
        header_index = i
        break

if header_index == -1:
    raise ValueError("[ERROR] No valid header found matching new column names.")

reader = csv.DictReader(lines[header_index:])
midnight = None

for row in reader:
    try:
        entry_dir = row["direction_entry"].strip().lower()
        exit_dir = row["direction_exit"].strip().lower()

        # Assign missing directions randomly, ensure entry != exit
        if not entry_dir:
            entry_dir = random.choice(list(DIRECTION_TO_EDGE_IN.keys()))
            print(f"[WARN] Missing entry direction, randomly assigned: {entry_dir}")

        if not exit_dir or exit_dir == entry_dir:
            # Pick exit direction different from entry
            exit_dir = random.choice([d for d in DIRECTION_TO_EDGE_OUT if d != entry_dir])
            print(f"[WARN] Missing or same exit direction, randomly assigned: {exit_dir}")

        from_edge = DIRECTION_TO_EDGE_IN.get(entry_dir)
        to_edge = DIRECTION_TO_EDGE_OUT.get(exit_dir)

        # Vehicle type priority: entry type, else exit type
        vtype = row["vehicle_type_entry"].strip()
        if not vtype:
            vtype = row["vehicle_type_exit"].strip()
            print(f"[WARN] Missing vehicle_type_entry, using vehicle_type_exit: {vtype}")
            
        if vtype not in VEHICLE_WHITELIST:
            print(f"[WARN] Skipping due to vehicle type '{vtype}' not in whitelist.")
            continue

        entered_time_str = row["entered_time"].strip()
        if not entered_time_str:
            entered_time_str = row["exit_time"].strip()
            print(f"[WARN] Missing entered_time, using exit_time: {entered_time_str}")


        entered_dt_utc = parse_iso_with_nanos(entered_time_str)
        entered_dt_ph = entered_dt_utc + PH_TZ_OFFSET

        if midnight is None:
            midnight = entered_dt_ph.replace(hour=0, minute=0, second=0, microsecond=0)

        entered_seconds = (entered_dt_ph - midnight).total_seconds()
        depart_time = estimate_depart(entered_seconds, from_edge, vtype)

        parsed_rows.append((depart_time, vtype, from_edge, to_edge))

    except Exception as e:
        print(f"[WARN] Skipping row due to error: {e}")

if not parsed_rows:
    raise ValueError("[ERROR] No valid vehicle trip data found.")

# === STEP 2: Generate trips ===
print("[INFO] Generating trips from direction-based input...")
parsed_rows.sort()
trips = Element("trips")

for vehicle_id, (depart, vtype, from_edge, to_edge) in enumerate(parsed_rows):
    SubElement(trips, "trip", {
        "id": f"{vtype}_{vehicle_id}",
        "type": vtype,
        "depart": str(depart),
        "from": from_edge,
        "to": to_edge
    })

# === STEP 3: Output to XML ===
tree = ElementTree(trips)
tree.write(OUTPUT_TRIPS, encoding="utf-8", xml_declaration=True)
print(f"[DONE] Wrote {vehicle_id + 1} trips to {OUTPUT_TRIPS}")
