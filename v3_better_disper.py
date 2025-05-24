import xml.etree.ElementTree as ET
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import geopandas as gpd
from shapely.geometry import Point
import matplotlib.patches as mpatches


# === Parameters ===
wind_speed = 1.0               # U (m/s)
mixing_height = 50.0           # H_wc (m)
wind_dir_deg = 90              # Wind direction in degrees (0=N, 90=E, 180=S, 270=W)
half_angle_deg = 45            # Angular spread for downwind sector

segments_per_lane = 10
receptors = [np.array([-1, -3])]  # Add more receptor coordinates as needed

# === Lane to edge mapping ===
EDGE_TO_LANE = {
    "-1232571604": "North",
    "-29251749#0": "East",
    "-4922743#4": "West",
    "29251749#0": "East",
    "1232571604": "North",
    "617654357#1": "South",
    "-617654357#1": "South",
    "4922743#4": "West",
    "237386421": "North"
}

LANE_DIRECTIONS = {
    "North": np.array([0, -1]),
    "South": np.array([0, 1]),
    "East": np.array([1, 0]),
    "West": np.array([-1, 0]),
}

LANE_LENGTHS = {
    "North": 74.5,
    "South": 24.46,
    "East": 47.32,
    "West": 71.45,
}

POLLUTANTS = ["CO", "CO2", "NOx", "PMx"]

# === Functions ===
def get_segment_positions(start, direction, length, num_segments):
    relative_positions = np.linspace(-length/2 + length/(2*num_segments),
                                     length/2 - length/(2*num_segments),
                                     num_segments)
    return [start + direction * d for d in relative_positions]

def is_downwind(src, receptor, wind_deg, half_angle):
    delta = receptor - src
    angle = (np.degrees(np.arctan2(delta[1], delta[0])) + 360) % 360
    downwind_center = (wind_deg + 180) % 360
    diff = min(abs(angle - downwind_center), 360 - abs(angle - downwind_center))
    return diff <= half_angle

# === Load and parse XML ===
file_path = "for_sd/sd_lane_emissions-dir.xml"  # Change if needed
tree = ET.parse(file_path)
root = tree.getroot()

rows = []

for interval in root.findall("interval"):
    for edge in interval.findall("edge"):
        edge_id = edge.get("id")
        lane_name = EDGE_TO_LANE.get(edge_id)
        if lane_name is None:
            continue

        direction = LANE_DIRECTIONS[lane_name]
        L = LANE_LENGTHS[lane_name]
        start_point = np.array([0.0, 0.0])

        for lane in edge.findall("lane"):
            for pollutant in POLLUTANTS:
                normed_val = float(lane.get(f"{pollutant}_normed", 0))
                emission_per_m = normed_val * 1e-6 / 3600  # g/km/h → kg/m/s

                segment_positions = get_segment_positions(start_point, direction, L, segments_per_lane)

                for i, pos in enumerate(segment_positions):
                    Q = emission_per_m * (L / segments_per_lane)  # kg/s
                    for ridx, receptor in enumerate(receptors):
                        r = np.linalg.norm(pos - receptor)
                        if r == 0:
                            r = 0.1
                        if not is_downwind(pos, receptor, wind_dir_deg, half_angle_deg):
                            continue

                        C_i = 10 * Q / (wind_speed * mixing_height * 0.1 * r)  # kg/m3
                        C_i_ug = C_i * 1e9

                        rows.append({
                            "lane": lane_name,
                            "pollutant": pollutant,
                            "segment_index": i,
                            "x": pos[0],
                            "y": pos[1],
                            "receptor_id": ridx,
                            "distance_to_receptor_m": r,
                            "Q_kg_per_s": Q,
                            "C_i_ug_per_m3": C_i_ug
                        })

# === Convert to DataFrame and save ===
df = pd.DataFrame(rows)
df.to_csv("gsa_output_concentrations.csv", index=False)
print(" [✓] Saved: gsa_output_concentrations.csv")

# === Export to shapefile for QGIS ===
geometry = [Point(xy) for xy in zip(df["x"], df["y"])]
gdf = gpd.GeoDataFrame(df, geometry=geometry, crs="EPSG:4326")
gdf.to_file("gsa_output_concentrations.shp")
print(" [✓] Saved: gsa_output_concentrations.shp")

import matplotlib.patches as patches

# === Plot emission segments and receptors ===
for ridx, receptor in enumerate(receptors):
    plt.figure(figsize=(8, 6))

    # Plot emission segments
    for lane in df["lane"].unique():
        lane_df = df[(df["lane"] == lane) & (df["receptor_id"] == ridx)]
        if lane_df.empty:
            continue
        sc = plt.scatter(
            lane_df["x"], lane_df["y"], 
            c=lane_df["Q_kg_per_s"], 
            cmap="viridis", s=60, edgecolor="k", label=f"{lane}"
        )

    # Plot receptor
    plt.scatter(receptor[0], receptor[1], color="red", marker="x", s=100, label=f"Receptor {ridx+1}")
    plt.text(receptor[0] + 0.5, receptor[1], f"Receptor {ridx+1}", fontsize=9, color="red")

    # Add colorbar
    cbar = plt.colorbar(sc)
    cbar.set_label("Emission Q (kg/s)")

    # Plot wind direction arrow (showing **where wind is going**)
    wind_rad = np.deg2rad((wind_dir_deg + 180) % 360)  # from wind_dir_deg
    arrow_length = max(df["x"].max() - df["x"].min(), df["y"].max() - df["y"].min()) * 0.1
    arrow_dx = arrow_length * np.cos(wind_rad)
    arrow_dy = arrow_length * np.sin(wind_rad)
    wind_center_x = df["x"].mean()
    wind_center_y = df["y"].mean()
    plt.arrow(wind_center_x, wind_center_y, arrow_dx, arrow_dy,
              head_width=1, head_length=1.5, fc="blue", ec="blue", label="Wind direction")
    plt.text(wind_center_x + arrow_dx, wind_center_y + arrow_dy, "Wind", color="blue")

    # Formatting
    plt.title(f"Emission Contributions to Receptor {ridx+1}")
    plt.xlabel("x (m)")
    plt.ylabel("y (m)")
    plt.axis("equal")
    plt.grid(True)
    plt.legend()
    plt.tight_layout()
    plt.savefig(f"for_sd/plots/gsa_emission_plot_receptor{ridx+1}.png", dpi=300)
    plt.close()
    print(f" [✓] Saved: gsa_emission_plot_receptor{ridx+1}.png")
