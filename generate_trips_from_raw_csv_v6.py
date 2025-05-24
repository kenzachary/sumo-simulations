import csv
from datetime import datetime, timedelta
from xml.etree.ElementTree import Element, SubElement, ElementTree
import xml.etree.ElementTree as ET
import random

PH_TZ_OFFSET = timedelta(hours=8)

# === CONFIGURATION ===
INPUT_CSV = "traffic_flow_may_17.csv"
OUTPUT_TRIPS = "v7_trips.trips.xml"
VTYPES_XML = "vtypes-1.add.xml"
NET_XML = "smaller.net.xml"
VEHICLE_WHITELIST = {"car", "motorcycle", "truck", "bus"}

# Map directions to actual edge IDs in your SUMO network
DIRECTION_TO_EDGE_IN = {
    "north": "237386421",
    "south": "-29251749#0",
    "east": "-617654357#1",
    "west": "4922743#4"
}

DIRECTION_TO_EDGE_OUT = {
    "north": "-1232571604",
    "south": "29251749#0",
    "east": "617654357#1",
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
def parse_iso_with_nanos(iso_str):
    if '.' in iso_str:
        base, frac = iso_str.split('.')
        frac = frac.rstrip('Z')
        frac = (frac + "000000")[:6]
        iso_str = f"{base}.{frac}Z"
    return datetime.strptime(iso_str, "%Y-%m-%dT%H:%M:%S.%fZ")

def estimate_depart(junction_time, from_edge, vtype):
    length = EDGE_LENGTHS.get(from_edge, 100)
    speed = SPEED_LOOKUP.get(vtype, 13.89)
    travel_time = length / speed
    return round(junction_time - travel_time)

# === STEP 1: Read CSV and process trips ===
print("[INFO] Reading CSV with new directional and vehicle type fields...")
parsed_rows = []

with open(INPUT_CSV, newline='') as f:
    lines = f.readlines()
header_index = -1
for i, line in enumerate(lines):
    if "entered_time" in line and "exit_time" in line and "direction_entry" in line and "direction_exit" in line and "vehicle_type_entry" in line and "vehicle_type_exit" in line:
        print(f"Header found at line {i}: {line.strip()}")
        header_index = i
        break
if header_index == -1:
    raise ValueError("No valid header found.")
    reader = csv.DictReader((lines[header_index:]))
    midnight = None

    for row in reader:
        try:
            in_dir_raw = row.get("direction_entry", "").strip().lower()
            out_dir_raw = row.get("direction_exit", "").strip().lower()
            time_str = row.get("entered_time", "").strip()
            vtype_entry = row.get("vehicle_type_entry", "").strip().lower()
            vtype_exit = row.get("vehicle_type_exit", "").strip().lower()
            count = 1  # Each row = 1 vehicle

            # Vehicle type fallback
            vtype = vtype_entry if vtype_entry else vtype_exit
            print(f"[DEBUG] Vehicle type: {vtype_entry} (entry), {vtype_exit} (exit)"
                  f" | Chosen: {vtype}")
            if not vtype:
                print("[WARN] Skipping row: missing vehicle type (entry and exit empty)")
                continue
            if vtype not in VEHICLE_WHITELIST:
                print(f"[WARN] Skipping row: vtype '{vtype}' not in whitelist")
                continue

            directions = list(DIRECTION_TO_EDGE_IN.keys())
            in_dir = in_dir_raw if in_dir_raw else None
            out_dir = out_dir_raw if out_dir_raw else None

            # Handle missing directions
            if not in_dir and not out_dir:
                in_dir, out_dir = random.sample(directions, 2)
                print(f"[WARN] Both directions missing. Randomly assigned: in={in_dir}, out={out_dir}")
            elif not in_dir:
                available = [d for d in directions if d != out_dir]
                in_dir = random.choice(available)
                print(f"[WARN] Missing direction_entry. Randomly assigned: {in_dir}")
            elif not out_dir:
                available = [d for d in directions if d != in_dir]
                out_dir = random.choice(available)
                print(f"[WARN] Missing direction_exit. Randomly assigned: {out_dir}")

            from_edge = DIRECTION_TO_EDGE_IN.get(in_dir)
            to_edge = DIRECTION_TO_EDGE_OUT.get(out_dir)

            reasons = []
            if from_edge is None:
                reasons.append("from_edge is None (invalid direction_entry)")
            if to_edge is None:
                reasons.append("to_edge is None (invalid direction_exit)")
            if from_edge == to_edge:
                reasons.append("from_edge equals to_edge (same edge)")

            if reasons:
                print(f"[WARN] Skipping row: in={in_dir}, out={out_dir}, vtype={vtype} | Reason(s): {', '.join(reasons)}")
                continue

            # Parse entered_time
            dt_utc = parse_iso_with_nanos(time_str)
            dt_ph = dt_utc + PH_TZ_OFFSET
            if midnight is None:
                midnight = dt_ph.replace(hour=0, minute=0, second=0, microsecond=0)

            junction_time = (dt_ph - midnight).total_seconds()
            adjusted_depart = estimate_depart(junction_time, from_edge, vtype)

            parsed_rows.append((adjusted_depart, vtype, from_edge, to_edge))
            print(f"[DEBUG] Row: {vtype}, depart: {adjusted_depart}, from: {from_edge}, to: {to_edge}")

        except Exception as e:
            print(f"[WARN] Skipping row due to error: {e}")
            continue

if not parsed_rows:
    raise ValueError("No valid vehicle trip data found.")

# === STEP 2: Generate trips ===
print("[INFO] Generating trips from parsed data...")
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

# === STEP 3: Write to XML ===
tree = ElementTree(trips)
tree.write(OUTPUT_TRIPS, encoding="utf-8", xml_declaration=True)
print(f"[DONE] Wrote {vehicle_id + 1} trips to {OUTPUT_TRIPS}")
