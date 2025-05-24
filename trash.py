import csv
import xml.etree.ElementTree as ET
from xml.etree.ElementTree import Element, SubElement, ElementTree
from datetime import datetime, timedelta
import random

# === CONFIGURATION ===
CAMERA_CSV = "traffic_flow_may_17.csv"
MANUAL_CSV = "mtc_data.csv"
VTYPES_XML = "vtypes-1.add.xml"
NET_XML = "smaller.net.xml"
OUTPUT_XML = "combined_trips.trips.xml"
PH_TZ_OFFSET = timedelta(hours=8)

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

VEHICLE_WHITELIST = {"car", "motorcycle", "truck", "bus"}

# === LOAD SPEED AND EDGE LENGTH DATA ===
def load_speeds_from_vtypes(vtypes_file):
    tree = ET.parse(vtypes_file)
    root = tree.getroot()
    return {
        v.attrib["id"]: float(v.attrib.get("maxSpeed", v.attrib.get("speed", 13.89)))
        for v in root.iter("vType")
    }

def load_edge_lengths(net_file):
    tree = ET.parse(net_file)
    edge_map = {}
    for edge in tree.findall("edge"):
        if edge.get("function") == "internal":
            continue
        for lane in edge.findall("lane"):
            edge_map[edge.attrib["id"]] = float(lane.attrib["length"])
    return edge_map

SPEED_LOOKUP = load_speeds_from_vtypes(VTYPES_XML)
EDGE_LENGTHS = load_edge_lengths(NET_XML)

def estimate_depart(junction_time, from_edge, vtype):
    length = EDGE_LENGTHS.get(from_edge, 100)
    speed = SPEED_LOOKUP.get(vtype, 13.89)
    return round(junction_time - (length / speed))

def parse_iso_with_nanos(iso_str):
    if not iso_str:
        return None
    if '.' in iso_str:
        base, frac = iso_str.split('.')
        frac = frac.rstrip('Z')
        frac = (frac + "000000")[:6]
        iso_str = f"{base}.{frac}Z"
    return datetime.strptime(iso_str, "%Y-%m-%dT%H:%M:%S.%fZ")

def validate_camera_headers(headers):
    required = {"entered_time", "exit_time", "direction_entry", "vehicle_id","direction_exit", "vehicle_type_entry", "vehicle_type_exit"}
    missing = required - set(h.strip().lower() for h in headers)
    if missing:
        raise ValueError(f"[ERROR] Camera CSV is missing required headers: {missing}")

def validate_manual_headers(headers):
    required = {"Time", "Vehicle", "Entry", "Exit"}
    missing = required - set(h.strip().lower() for h in headers)
    if missing:
        raise ValueError(f"[ERROR] Manual count CSV is missing required headers: {missing}")

def parse_time_to_seconds(time_str):
    dt = datetime.strptime(time_str.strip(), "%H:%M")
    return dt.hour * 3600 + dt.minute * 60


# === STEP 1: PARSE CAMERA DATA ===
print("[INFO] Processing camera CSV...")
camera_keys = {}
camera_trips = []
midnight = None

with open(CAMERA_CSV) as f:
    
    reader = csv.DictReader(f)
    validate_camera_headers(reader.fieldnames)
    for row in reader:
        entry_dir = row["direction_entry"].strip().lower()
        exit_dir = row["direction_exit"].strip().lower()

        if not entry_dir:
            entry_dir = random.choice(list(DIRECTION_TO_EDGE_IN))
        if not exit_dir or exit_dir == entry_dir:
            exit_dir = random.choice([d for d in DIRECTION_TO_EDGE_OUT if d != entry_dir])

        vtype = row["vehicle_type_entry"].strip() or row["vehicle_type_exit"].strip()
        if vtype not in VEHICLE_WHITELIST:
            continue

        from_edge = DIRECTION_TO_EDGE_IN[entry_dir]
        to_edge = DIRECTION_TO_EDGE_OUT[exit_dir]

        timestamp_str = row["entered_time"].strip() or row["exit_time"].strip()
        dt = parse_iso_with_nanos(timestamp_str)
        if dt is None:
            print(f"[WARN] Skipping row with missing timestamp: {row}")
            continue
        dt += PH_TZ_OFFSET

        if midnight is None:
            midnight = dt.replace(hour=0, minute=0, second=0, microsecond=0)

        seconds = (dt - midnight).total_seconds()
        depart = estimate_depart(seconds, from_edge, vtype)
        minute = int(seconds) // 60

        key = (minute, entry_dir, exit_dir, vtype)
        camera_keys[key] = camera_keys.get(key, 0) + 1
        camera_trips.append((depart, vtype, from_edge, to_edge))

# === STEP 2: LOAD MANUAL COUNTS ===
print("[INFO] Processing manual counts...")
manual_counts = {}

with open(MANUAL_CSV) as f:
    reader = csv.DictReader(f)
    validate_manual_headers(reader.fieldnames)
    for row in reader:
        try:
            dt = datetime.strptime(row["time"], "%Y-%m-%d %H:%M:%S")
            minute = (dt - dt.replace(hour=0, minute=0, second=0)).total_seconds() // 60
            minute = int(minute)

            vtype = row["vehicle"].strip().lower()
            entry = row["entry"].strip().lower()
            exit_ = row["exit"].strip().lower()

            if vtype not in VEHICLE_WHITELIST:
                print(f"[WARN] Skipping due to vehicle type '{vtype}' not in whitelist.")
                continue

            key = (minute, entry, exit_, vtype)
            manual_counts[key] = manual_counts.get(key, 0) + 1
        except Exception as e:
            print(f"[WARN] Skipping manual row: {e}")

# === STEP 3: GENERATE SYNTHETIC TRIPS FOR MISSING ===
print("[INFO] Generating synthetic trips to fill gaps...")
supplemental_trips = []

for key, manual_count in manual_counts.items():
    camera_count = camera_keys.get(key, 0)
    missing = manual_count - camera_count
    if missing <= 0:
        continue

    minute, entry, exit_, vtype = key
    from_edge = DIRECTION_TO_EDGE_IN[entry]
    to_edge = DIRECTION_TO_EDGE_OUT[exit_]
    base_time = midnight + timedelta(minutes=minute)

    for i in range(missing):
        jitter = random.randint(0, 59)
        fake_time = base_time + timedelta(seconds=jitter)
        seconds = (fake_time - midnight).total_seconds()
        depart = estimate_depart(seconds, from_edge, vtype)
        supplemental_trips.append((depart, vtype, from_edge, to_edge))

# === STEP 4: COMBINE AND EXPORT ===
print("[INFO] Writing to XML...")
all_trips = camera_trips + supplemental_trips
all_trips.sort()

trips_elem = Element("trips")

for i, (depart, vtype, from_edge, to_edge) in enumerate(all_trips):
    SubElement(trips_elem, "trip", {
        "id": f"{vtype}_{i}",
        "type": vtype,
        "depart": str(depart),
        "from": from_edge,
        "to": to_edge
    })

ElementTree(trips_elem).write(OUTPUT_XML, encoding="utf-8", xml_declaration=True)
print(f"[DONE] Wrote {len(all_trips)} total trips to {OUTPUT_XML}")
