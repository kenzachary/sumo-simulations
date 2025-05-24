import xml.etree.ElementTree as ET
import numpy as np
import pandas as pd
import math
import os

# Parameters
U = 1.0  # wind speed in m/s
H_wc = 50.0  # mixing height in m
receptor = np.array([-9, 10])  # receptor position (x, y) in meters
wind_direction_deg = 0.0  # wind blowing from the North (0°), East = 90°

# Angle filter
angle_tolerance = 45  # degrees

# Mapping: lane to merged side
LANE_TO_SIDE = {
    "North In": "North",
    "North Out": "North",
    "South In": "South",
    "South Out": "South",
    "East In": "East",
    "East Out": "East",
    "West In": "West",
    "West Out": "West"
}

# Lengths and directions for each lane
LANE_INFO = {
    "North In": {"dir": (0, -1), "length": 74.5},
    "North Out": {"dir": (0, 1), "length": 74.5},
    "South In": {"dir": (0, 1), "length": 24.46},
    "South Out": {"dir": (0, -1), "length": 24.46},
    "East In": {"dir": (-1, 0), "length": 47.32},
    "East Out": {"dir": (1, 0), "length": 47.32},
    "West In": {"dir": (1, 0), "length": 71.45},
    "West Out": {"dir": (-1, 0), "length": 71.45}
}

EDGE_TO_LANE = {
    "-1232571604": "North Out",
    "-29251749#0": "East In",
    "-4922743#4": "West Out",
    "29251749#0": "East Out",
    "1232571604": "North In",
    "617654357#1": "South Out",
    "-617654357#1": "South In",
    "4922743#4": "West In",
    "237386421": "North In"
}

POLLUTANTS = ["CO", "CO2", "NOx", "PMx"]
segments_per_lane = 10

# Helper
def get_segment_position(start, direction, length, seg_index, num_segments):
    segment_length = length / num_segments
    offset = (seg_index + 0.5) * segment_length
    return start + direction * offset

def angle_between(v1, v2):
    unit_v1 = v1 / np.linalg.norm(v1)
    unit_v2 = v2 / np.linalg.norm(v2)
    dot = np.clip(np.dot(unit_v1, unit_v2), -1.0, 1.0)
    return np.degrees(np.arccos(dot))

# Wind vector (coming from wind_direction_deg, so towards receptor)
wind_rad = math.radians((wind_direction_deg + 180) % 360)
wind_vec = np.array([math.cos(wind_rad), math.sin(wind_rad)])

# Load XML
file_path = "for_sd/sd_lane_emissions-dir.xml"
tree = ET.parse(file_path)
root = tree.getroot()

# Collect total Q per side
results = []
for interval in root.findall("interval"):
    for edge in interval.findall("edge"):
        edge_id = edge.get("id")
        lane_name = EDGE_TO_LANE.get(edge_id)
        if not lane_name:
            print(f"Warning: Lane name not found for edge ID {edge_id}")
            continue
        side = LANE_TO_SIDE[lane_name]
        info = LANE_INFO[lane_name]
        length = info["length"]
        direction = np.array(info["dir"])
        start_point = -0.5 * length * direction

        for lane in edge.findall("lane"):
            for pollutant in POLLUTANTS:
                normed_val = float(lane.get(f"{pollutant}_normed", 0))
                emission_per_m = normed_val * 1e-6 / 3600  # kg/m/s

                for i in range(segments_per_lane):
                    pos = get_segment_position(start_point, direction, length, i, segments_per_lane)
                    vec_to_receptor = receptor - pos
                    dist = np.linalg.norm(vec_to_receptor)
                    if dist == 0:
                        dist = 0.1
                    angle = angle_between(vec_to_receptor, wind_vec)
                    if angle > angle_tolerance:
                        print(f" [!] Angle {angle:.2f}° exceeds tolerance {angle_tolerance}° for side {side}, segment {i}")
                        continue  # outside wind sector

                    Q_i = emission_per_m * (length / segments_per_lane)  # kg/s
                    C_i = 10 * Q_i / (U * H_wc * (0.1*dist))  # kg/m³
                    results.append({
                        "side": side,
                        "pollutant": pollutant,
                        "segment_index": i,
                        "x": pos[0],
                        "y": pos[1],
                        "Q_kg_per_s": Q_i,
                        "C_i_kg_per_m3": C_i,
                        "C_i_ug_per_m3": C_i * 1e9,
                        "distance_to_receptor_m": dist,
                        "angle_deg": angle
                    })

# Export to CSV
if len(results) == 0:
    print(" [!] No results to save.")

else:
    df = pd.DataFrame(results)
    os.makedirs("for_sd", exist_ok=True)
    df.to_csv("for_sd/sd_side_segments_concentration.csv", index=False)
    print(" [✓] SUCCESS! Saved: for_sd/sd_side_segments_concentration.csv")