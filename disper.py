import xml.etree.ElementTree as ET
import numpy as np
import pandas as pd

# Settings
POLLUTANTS = ["NOx", "CO", "CO2", "PMx"]
G_KM_H_TO_KG_M_S = 2.7778e-7  # conversion factor
segments_per_lane = 10
U = 1.0                      # wind speed (m/s)
H_wc = 50.0                  # mixing height (m)
receptor = np.array([0, 0])  # center of intersection

# Direction unit vectors
lane_directions = {
    "North In": (0, -1),
    "North Out": (0, 1),
    "South In": (0, 1),
    "South Out": (0, -1),
    "East In": (-1, 0),
    "East Out": (1, 0),
    "West In": (1, 0),
    "West Out": (-1, 0),
}

# Edge → human-readable lane name
edge_to_lane = {
    "-1232571604": "North Out",
    "-29251749#0": "South In",
    "-4922743#4": "West Out",
    "29251749#0": "South Out",
    "617654357#1": "East Out",
    "-617654357#1": "East In",
    "4922743#4": "West In",
    "237386421": "North In",
}

# Lane lengths (meters)
lane_lengths = {
    "North In": 74.5,
    "North Out": 74.5,
    "South In": 24.46,
    "South Out": 24.46,
    "East In": 47.32,
    "East Out": 47.32,
    "West In": 71.45,
    "West Out": 71.45,
}

# Helper: segment position
def get_segment_position(start, direction, length, seg_index, num_segments):
    segment_length = length / num_segments
    offset = (seg_index + 0.5) * segment_length
    return start + direction * offset

# Parse emissions file
tree = ET.parse("for_sd/sd_lane_emissions-dir.xml")
root = tree.getroot()

results = []

for interval in root.findall("interval"):
    for edge in interval.findall("edge"):
        edge_id = edge.get("id")
        lane_name = edge_to_lane.get(edge_id)

        if lane_name is None:
            continue

        L = lane_lengths[lane_name]
        direction = np.array(lane_directions[lane_name])
        start_point = -0.5 * L * direction

        # Get normed emissions for each pollutant
        for lane in edge.findall("lane"):
            for pollutant in POLLUTANTS:
                attr = f"{pollutant}_normed"
                if attr not in lane.attrib:
                    continue
                normed = float(lane.attrib[attr])  # g/km/h
                E = normed * G_KM_H_TO_KG_M_S      # kg/(m·s)

                total_C = 0
                for i in range(segments_per_lane):
                    pos = get_segment_position(start_point, direction, L, i, segments_per_lane)
                    r = np.linalg.norm(pos - receptor)
                    r = max(r, 0.1)  # avoid div by zero

                    segment_length = L / segments_per_lane
                    Q = E * segment_length  # kg/s per segment
                    C_i = 10 * Q / (U * H_wc * r)  # kg/m³

                    total_C += C_i

                results.append({
                    "lane": lane_name,
                    "pollutant": pollutant,
                    "total_concentration_μg_per_m³": total_C * 1e9
                })

# Save or inspect
df = pd.DataFrame(results)
df = df.groupby(["lane", "pollutant"], as_index=False).sum()

# View or export
print(df)
# df.to_csv("receptor_concentrations.csv", index=False)
