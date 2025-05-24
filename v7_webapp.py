import xml.etree.ElementTree as ET
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from scipy.interpolate import griddata
from scipy.interpolate import Rbf


# === Parameters ===
wind_speed = 1.0               # U (m/s)
mixing_height = 50.0           # H_wc (m)
wind_dir_deg = 217             # Wind direction in degrees (0=N, 90=E, 180=S, 270=W)
half_angle_deg = 45            # Angular spread for downwind sector

segments_per_lane = 10

# Grid parameters
grid_res = 1.0
x_range = np.arange(-30, 30 + grid_res, grid_res)
y_range = np.arange(-30, 30 + grid_res, grid_res)
grid_points = np.array([[x, y] for x in x_range for y in y_range])

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

# === Directories ===
Path("gsa_hourly").mkdir(exist_ok=True)
Path("for_sd/plots").mkdir(parents=True, exist_ok=True)

# === Functions ===
def get_segment_position(start, direction, length, seg_index, num_segments):
    segment_length = length / num_segments
    offset = (seg_index + 0.5) * segment_length
    return start + direction * offset

def is_downwind(src, receptor, wind_deg, half_angle):
    delta = receptor - src
    angle = (np.degrees(np.arctan2(delta[1], delta[0])) + 360) % 360
    downwind_center = (wind_deg + 180) % 360
    diff = min(abs(angle - downwind_center), 360 - abs(angle - downwind_center))
    return diff <= half_angle


def plot_intersection_outline(ax, segments_per_lane=segments_per_lane):
    for edge_id, lane_name in EDGE_TO_LANE.items():
        direction = LANE_DIRECTIONS[lane_name]
        L = LANE_LENGTHS[lane_name]
        start_point = -0.5 * L * direction
        
        # Plot lane as a thick line made of segments
        lane_points = [
            get_segment_position(start_point, direction, L, i, segments_per_lane)
            for i in range(segments_per_lane + 1)
        ]
        lane_points = np.array(lane_points)
        
        ax.plot(lane_points[:, 0], lane_points[:, 1], color='cyan', linewidth=3, alpha=0.7)


# === Load and parse XML ===
file_path = "for_sd/sd_lane_emissions-dir.xml"  # Change if needed
tree = ET.parse(file_path)
root = tree.getroot()

all_concentration_rows = []

for interval in root.findall("interval"):
    start_time_sec = float(interval.get("begin", 0))
    hour = int(start_time_sec // 3600)

    for edge in interval.findall("edge"):
        edge_id = edge.get("id")
        lane_name = EDGE_TO_LANE.get(edge_id)
        if lane_name is None:
            continue

        direction = LANE_DIRECTIONS[lane_name]
        L = LANE_LENGTHS[lane_name]
        start_point = -0.5 * L * direction

        for lane in edge.findall("lane"):
            for pollutant in POLLUTANTS:
                normed_val = float(lane.get(f"{pollutant}_normed", 0))
                emission_per_m = normed_val * 1e-6 / 3600  # g/km/h → kg/m/s

                for i in range(segments_per_lane):
                    pos = get_segment_position(start_point, direction, L, i, segments_per_lane)
                    Q = emission_per_m * (L / segments_per_lane)  # kg/s

                    for gp in grid_points:
                        if not is_downwind(pos, gp, wind_dir_deg, half_angle_deg):
                            continue
                        r = np.linalg.norm(pos - gp)
                        if r == 0:
                            r = 0.1

                        C_i = 10 * Q / (wind_speed * mixing_height * 0.1 * r)  # kg/m³
                        C_i_ug = C_i * 1e9  # μg/m³

                        all_concentration_rows.append({
                            "hour": hour,
                            "pollutant": pollutant,
                            "x": gp[0],
                            "y": gp[1],
                            "C_i_ug_per_m3": C_i_ug
                        })

# === Aggregate concentrations at grid points ===
df = pd.DataFrame(all_concentration_rows)
total_df = df.groupby(["hour", "pollutant", "x", "y"])["C_i_ug_per_m3"].sum().reset_index()

total_df.to_csv("gsa_hourly/total_receptor_concentrations.csv", index=False)
print(" [✓] Saved: gsa_hourly/total_receptor_concentrations.csv")


# === Interpolated heatmaps per hour and pollutant ===
heatmap_paths = []
for (hour, pollutant), group in total_df.groupby(["hour", "pollutant"]):
    xi, yi = np.meshgrid(x_range, y_range)
    # Use RBF interpolation:
    rbf = Rbf(group.x, group.y, group.C_i_ug_per_m3, function='linear')  # 'linear' or try 'multiquadric', 'thin_plate'
    zi = rbf(xi, yi)

    plt.figure(figsize=(8, 6))
    plt.contourf(xi, yi, zi, levels=100, cmap="hot")
    plt.colorbar(label="μg/m³")

    ax = plt.gca()
    plot_intersection_outline(ax)

    plt.title(f"{pollutant} Concentration - Hour {hour}")
    plt.xlabel("X (m)")
    plt.ylabel("Y (m)")
    plt.axis("equal")
    path = f"for_sd/plots/heatmap_hour{hour}_{pollutant}.png"
    plt.savefig(path, dpi=300)
    plt.close()
    heatmap_paths.append(path)

heatmap_paths[:5]  # show first few output file paths
