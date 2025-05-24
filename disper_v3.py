import xml.etree.ElementTree as ET
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import os
from matplotlib import colormaps
from scipy.interpolate import griddata
import os

# Parameters
#receptor = np.array([0, 0])  # Center of intersection
receptors = [np.array([0, 0]), np.array([20, 0]), np.array([0, 30])]  # Example: three receptor points
U = 1.0                      # Wind speed (m/s)
H_wc = 50.0                 # Mixing height (m)
segments_per_lane = 10

# Lane name mapping
EDGE_TO_LANE = {
    "-1232571604": "North Out",
    "-29251749#0": "South In",
    "-4922743#4": "West Out",
    "29251749#0": "South Out",
    "1232571604": "North In",
    "617654357#1": "East Out",
    "-617654357#1": "East In",
    "4922743#4": "West In",
    "237386421": "North In"
}

LANE_DIRECTIONS = {
    "North In": (0, -1),
    "North Out": (0, 1),
    "South In": (0, 1),
    "South Out": (0, -1),
    "East In": (-1, 0),
    "East Out": (1, 0),
    "West In": (1, 0),
    "West Out": (-1, 0),
}

LANE_LENGTHS = {
    "North In": 74.5,
    "North Out": 74.5,
    "South In": 24.46,
    "South Out": 24.46,
    "East In": 47.32,
    "East Out": 47.32,
    "West In": 71.45,
    "West Out": 71.45,
}


POLLUTANTS = ["CO", "CO2", "NOx", "PMx"]

# Helper: get segment position
def get_segment_position(start, direction, length, seg_index, num_segments):
    segment_length = length / num_segments
    offset = (seg_index + 0.5) * segment_length
    return start + direction * offset

# Load the emissions.xml file
file_path = "for_sd/sd_lane_emissions-dir.xml"  # Replace with your actual file path
tree = ET.parse(file_path)
root = tree.getroot()

results = []

# Parse XML and compute concentrations
for interval in root.findall("interval"):
    for edge in interval.findall("edge"):
        edge_id = edge.get("id")
        for lane in edge.findall("lane"):
            base_edge_id = edge_id
            lane_name = EDGE_TO_LANE.get(base_edge_id)
            if lane_name is None:
                continue

            direction = np.array(LANE_DIRECTIONS[lane_name])
            L = LANE_LENGTHS[lane_name]
            print(f"Processing lane: {lane_name} with direction {direction}")
            start_point = -0.5 * L * direction

            for pollutant in POLLUTANTS:
                normed_val = float(lane.get(f"{pollutant}_normed", 0))
                emission_per_m = normed_val * 1e-6 / 3600  # g/km/h to kg/m/s

                for i in range(segments_per_lane):
                    pos = get_segment_position(start_point, direction, L, i, segments_per_lane)
                    
                    for receptor_idx, receptor in enumerate(receptors):
                        r = np.linalg.norm(pos - receptor)
                        if r == 0:
                            r = 0.1
                        Q = emission_per_m * (L / segments_per_lane)
                        C_i = 10 * Q / (U * H_wc * r)
                        results.append({
                            "lane": lane_name,
                            "pollutant": pollutant,
                            "segment_index": i,
                            "x": pos[0],
                            "y": pos[1],
                            "receptor_idx": receptor_idx,
                            "receptor_x": receptor[0],
                            "receptor_y": receptor[1],
                            "distance_to_receptor_m": r,
                            "Q_kg_per_s": Q,
                            "C_i_kg_per_m3": C_i
                        })

# Convert to DataFrame
df = pd.DataFrame(results)
df["C_i_ug_per_m3"] = df["C_i_kg_per_m3"] * 1e9

# Aggregated results
lane_pollutant_agg = df.groupby(["lane", "pollutant"])["C_i_ug_per_m3"].sum().reset_index(name="total_concentration_μg_per_m³")
df["direction"] = df["lane"].str.extract(r"(North|South|East|West)")
df["flow"] = df["lane"].str.extract(r"(In|Out)")
dir_pollutant_agg = df.groupby(["direction", "pollutant"])["C_i_ug_per_m3"].sum().reset_index(name="total_concentration_μg_per_m³")
flow_pollutant_agg = df.groupby(["flow", "pollutant"])["C_i_ug_per_m3"].sum().reset_index(name="total_concentration_μg_per_m³")
overall_pollutant_agg = df.groupby("pollutant")["C_i_ug_per_m3"].sum().reset_index(name="total_concentration_μg_per_m³")

# --- NEW: Aggregate by receptor and pollutant ---
receptor_pollutant_agg = (
    df.groupby(["receptor_idx", "receptor_x", "receptor_y", "pollutant"])["C_i_ug_per_m3"]
    .sum()
    .reset_index(name="total_concentration_μg_per_m³")
)

# To save or inspect the outputs:
lane_pollutant_agg.to_csv("for_sd/sd_lane_concentrations.csv", index=False)
print(" [✓] Saved: for_sd/sd_lane_concentrations.csv")
dir_pollutant_agg.to_csv("for_sd/sd_direction_concentrations.csv", index=False)
print(" [✓] Saved: for_sd/sd_direction_concentrations.csv")
flow_pollutant_agg.to_csv("for_sd/sd_flow_concentrations.csv", index=False)
print(" [✓] Saved: for_sd/sd_flow_concentrations.csv")
overall_pollutant_agg.to_csv("for_sd/sd_total_concentrations.csv", index=False)
print(" [✓] Saved: for_sd/sd_total_concentrations.csv")
receptor_pollutant_agg.to_csv("for_sd/sd_receptor_concentrations.csv", index=False)
print(" [✓] Saved: for_sd/sd_receptor_concentrations.csv")


# --- SETTINGS ---
POLLUTANTS = ["CO", "CO2", "NOx", "PMx"]
grid_res = 200  # Increase for higher resolution
cmap = 'viridis'
output_dir = "for_sd/plots"
os.makedirs(output_dir, exist_ok=True)

# --- LOOP OVER POLLUTANTS ---
for pollutant in POLLUTANTS:
    df_plot = df[df["pollutant"] == pollutant].copy()
    
    if df_plot.empty:
        print(f"[!] Skipping {pollutant} — no data available.")
        continue

    # --- Extract data ---
    x_vals = df_plot["x"].values
    y_vals = df_plot["y"].values
    z_vals = df_plot["C_i_ug_per_m3"].values

    # --- Define grid ---
    xi = np.linspace(x_vals.min(), x_vals.max(), grid_res)
    yi = np.linspace(y_vals.min(), y_vals.max(), grid_res)
    xi, yi = np.meshgrid(xi, yi)

    # --- Interpolate ---
    zi = griddata((x_vals, y_vals), z_vals, (xi, yi), method='cubic')

        # --- Plot ---
    fig, ax = plt.subplots(figsize=(8, 8))
    c = ax.contourf(xi, yi, zi, levels=100, cmap=cmap)

    # --- Colorbar ---
    cbar = fig.colorbar(c)
    cbar.set_label(f"{pollutant} concentration (μg/m³)")

    # --- Plot X and Y axes as solid lines ---
    ax.axhline(0, color='black', linewidth=1, linestyle='-')  # X-axis
    ax.axvline(0, color='black', linewidth=1, linestyle='-')  # Y-axis

    # --- Overlay emission points ---
    ax.scatter(x_vals, y_vals, color='white', edgecolor='black', s=15, label='Emission Source Points', zorder=10)

    # --- Labels & format ---
    ax.set_title(f"Interpolated Concentration Map – {pollutant}")
    ax.set_xlabel("x (m)")
    ax.set_ylabel("y (m)")
    ax.set_aspect("equal")
    ax.grid(True)
    ax.legend(loc="upper right")

    # --- Save ---
    output_path = os.path.join(output_dir, f"{pollutant}_interpolated.png")
    plt.tight_layout()
    plt.savefig(output_path, dpi=300)
    plt.close(fig)
    print(f"[✓] Saved: {output_path}")

