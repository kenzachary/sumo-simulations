import csv
from datetime import datetime, timedelta
from xml.etree.ElementTree import Element, SubElement, ElementTree
import xml.etree.ElementTree as ET
import random
from collections import defaultdict
from xml.etree.ElementTree import parse

PH_TZ_OFFSET = timedelta(hours=8)

# === CONFIGURATION ===
INPUT_CSV = "mtc.csv"
OUTPUT_TRIPS = "v_trips.trips.xml"
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

def parse_time_to_seconds(time_str):
    dt = datetime.strptime(time_str.strip(), "%H:%M")
    return dt.hour * 3600 + dt.minute * 60

def load_existing_vehicle_ids(existing_trips_file):
    existing_ids = set()
    tree = ET.parse(existing_trips_file)
    root = tree.getroot()
    for trip in root.findall("trip"):
        trip_id = trip.attrib.get("id")
        if trip_id:
            existing_ids.add(trip_id)
    return existing_ids



# === STEP 1: Read CSV and detect header ===
print("[INFO] Reading CSV with directional fields...")
parsed_rows = []

with open(INPUT_CSV, newline='') as f:
    lines = f.readlines()

header_index = -1
required_headers = [
    "Time",
    "Vehicle",
    "Entry",
    "Exit",
]

for i, line in enumerate(lines):
    if all(h in line for h in required_headers):
        print(f"[INFO] Header found at line {i}: {line.strip()}")
        header_index = i
        break

if header_index == -1:
    raise ValueError("[ERROR] No valid header found matching new column names.")

cleaned_lines = [line for line in lines[header_index:] if line.strip()]
reader = csv.DictReader(cleaned_lines)

midnight = None

for row in reader:
    try:
        if "Entry" not in row or "Exit" not in row:
            print(f"[WARN] Skipping row due to missing 'Entry' or 'Exit': {row}")
            continue

        entry_dir = row["Entry"].strip().lower()
        exit_dir = row["Exit"].strip().lower()
        #print(f"[DEBUG] Entry: {entry_dir}, Exit: {exit_dir}")

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
        if from_edge is None:
            print(f"[WARN] Unknown entry direction '{entry_dir}', skipping row.")
            continue

        if to_edge is None:
            print(f"[WARN] Unknown exit direction '{exit_dir}', skipping row.")
            continue

        # Vehicle type priority: entry type, else exit type
        vtype = row["Vehicle"].strip().lower().replace('\xa0', '') 
        #print(f"[DEBUG] Vehicle type: {vtype}")


        if not vtype:
            print("[WARN] Missing vehicle type, skipping row.")
            continue

        if vtype not in VEHICLE_WHITELIST:
            print(f"[WARN] Skipping due to vehicle type '{vtype}' not in whitelist.")
            continue

        entered_time_str = row["Time"].strip()
        if not entered_time_str:
            print("[WARN] Missing entered_time, skipping row.")
            continue


        #entered_dt_utc = parse_iso_with_nanos(entered_time_str)
        #entered_dt_ph = entered_dt_utc + PH_TZ_OFFSET

        #if midnight is None:
         #   midnight = entered_dt_ph.replace(hour=0, minute=0, second=0, microsecond=0)






        entered_seconds = parse_time_to_seconds(entered_time_str)
        #print(f"[DEBUG] Parsed time: {entered_seconds} seconds")
        depart_offsets = defaultdict(set)

        # Estimate the base departure time
        depart_time = estimate_depart(entered_seconds, from_edge, vtype)
        #print(f"[DEBUG] Estimated departure time: {depart_time} seconds")
        
        # Determine the base minute (i.e., floor to nearest 60)
        base_minute = (depart_time // 60) * 60
        used_offsets = depart_offsets[base_minute]

        if len(used_offsets) >= 9:
            print(f"[WARN] More than 60 vehicles detected at {base_minute}, skipping row.")
            continue

        # Random unused offset between 0 and 59
        available_offsets = list(set(range(60)) - used_offsets)
        random_offset = random.choice(available_offsets)
        depart_offsets[base_minute].add(random_offset)

        # Final adjusted departure time
        adjusted_depart_time = base_minute + random_offset

        #print(f"[DEBUG] Estimated base depart: {depart_time}, randomized: {adjusted_depart_time}")
        parsed_rows.append((adjusted_depart_time, vtype, from_edge, to_edge))



    except Exception as e:
        print(f"[WARN] Skipping row due to error: {e}")

if not parsed_rows:
    raise ValueError("[ERROR] No valid vehicle trip data found.")



# === STEP 1.5: Load existing trips and collect occupied trip keys ===
existing_trip_keys = set()
existing_ids = set()

try:
    tree_existing = parse("v5_trips.trips.xml")
    root_existing = tree_existing.getroot()
    total_trips_in_file = len(root_existing.findall("trip"))
    print(f"[INFO] Found {total_trips_in_file} existing trips in v5_trips.trips.xml")

    for trip in root_existing.findall("trip"):
        depart = int(float(trip.attrib["depart"]))
        vtype = trip.attrib.get("type")
        from_edge = trip.attrib.get("from")
        to_edge = trip.attrib.get("to")
        trip_id = trip.attrib.get("id")

        depart_minute = depart // 90
        key = (vtype, from_edge, to_edge, depart_minute)
        existing_trip_keys.add(key)
        if trip_id:
            existing_ids.add(trip_id)

    print(f"[INFO] Loaded {len(existing_trip_keys)} existing trip keys from trips file.")
except FileNotFoundError:
    print("[INFO] No existing trip file found, starting fresh.")
    root_existing = Element("trips")  # Create a new root



# === STEP 2: Generate trips ===
print("[INFO] Generating trips from direction-based input...")
parsed_rows.sort()
trips = root_existing  # Reuse the parsed XML root from earlier

countt = 0
for vehicle_id, (depart, vtype, from_edge, to_edge) in enumerate(parsed_rows):
    depart_minute = depart // 90
    key = (vtype, from_edge, to_edge, depart_minute)

    if key in existing_trip_keys:
        # Exact trip already exists for this minute window
        #print(f"[INFO] Skipping trip due to existing trip key {key}")

        continue

    trip_id = f"{vtype}_{vehicle_id + 1000000000}"  # Ensure unique trip ID  #You should not reach this
    if trip_id in existing_ids:
        #print(f"[INFO] Skipping duplicate trip ID: {trip_id}")
        continue

    # Add to sets to reserve this trip key and id
    existing_trip_keys.add(key)
    existing_ids.add(trip_id)

    SubElement(trips, "trip", {
        "id": trip_id,
        "type": vtype,
        "depart": str(depart),
        "from": from_edge,
        "to": to_edge
    })

    countt += 1

# === STEP 2.5: Sort all <trip> elements by depart time ===
sorted_trips = sorted(trips.findall("trip"), key=lambda t: float(t.attrib["depart"]))
for trip in list(trips):
    trips.remove(trip)  # Remove all existing trips
for trip in sorted_trips:
    trips.append(trip)  # Re-insert in sorted order


# === STEP 3: Output to XML ===
tree = ElementTree(trips)
tree.write("v5_trips.trips.xml", encoding="utf-8", xml_declaration=True)
print(f"[INFO] Found {total_trips_in_file} existing trips in v5_trips.trips.xml")
print(f"[DONE] Wrote {countt} trips to v5_trips.trips.xml")
print(f"[DONE] Total trips in file: {countt+total_trips_in_file}")