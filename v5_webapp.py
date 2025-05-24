import xml.etree.ElementTree as ET
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import geopandas as gpd
from shapely.geometry import Point
from pathlib import Path
import seaborn as sns

# === Parameters ===
wind_speed = 1.0               # U (m/s)
mixing_height = 50.0           # H_wc (m)
wind_dir_deg = 217             # Wind direction in degrees (0=N, 90=E, 180=S, 270=W)
half_angle_deg = 45            # Angular spread for downwind sector

segments_per_lane = 10
receptors = [np.array([-5, -2])]  # Add more receptor coordinates as needed

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
    """
    Returns the position of the center of a segment along a lane.

    Parameters:
        start: np.array, start point of the lane (numpy array)
        direction: np.array, unit vector direction of the lane (numpy array)
        length: float, total length of the lane
        seg_index: int, index of the segment (0-based)
        num_segments: int, total number of segments

    Returns:
        np.array: position (x, y) of the segment center
    """
    segment_length = length / num_segments
    offset = (seg_index + 0.5) * segment_length
    return start + direction * offset

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
                    for ridx, receptor in enumerate(receptors):
                        r = np.linalg.norm(pos - receptor)
                        if r == 0:
                            r = 0.1
                        if not is_downwind(pos, receptor, wind_dir_deg, half_angle_deg):
                            continue

                        C_i = 10 * Q / (wind_speed * mixing_height * 0.1 * r)  # kg/m³
                        C_i_ug = C_i * 1e9  # μg/m³

                        rows.append({
                            "hour": hour,
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

# === Convert to DataFrame ===
df = pd.DataFrame(rows)

# === Total concentration per receptor, per hour, per pollutant ===
receptor_totals = (
    df.groupby(["hour", "pollutant", "receptor_id"])["C_i_ug_per_m3"]
    .sum()
    .reset_index()
    .rename(columns={"C_i_ug_per_m3": "total_concentration_ug_per_m3"})
)
receptor_totals.to_csv("gsa_hourly/v5-total_receptor_concentrations.csv", index=False)
print(" [✓] Saved: gsa_hourly/v5-total_receptor_concentrations.csv")


# === Save separate CSVs per receptor ===
for rid, df_r in receptor_totals.groupby("receptor_id"):
    out_path = f"gsa_hourly/receptor_{rid}_hourly_concentrations.csv"
    df_r.to_csv(out_path, index=False)
    print(f" [✓] Saved: {out_path}")


# === Pivot version: pollutants as columns ===
for rid, df_r in receptor_totals.groupby("receptor_id"):
    pivot_df = df_r.pivot(index="hour", columns="pollutant", values="total_concentration_ug_per_m3")
    pivot_df = pivot_df.reset_index()
    pivot_out = f"gsa_hourly/receptor_{rid}_hourly_concentrations_pivot.csv"
    pivot_df.to_csv(pivot_out, index=False)
    print(f" [✓] Saved (pivot): {pivot_out}")

'''''''''''''''''
# === Line plots of receptor concentrations over time ===
for pollutant in POLLUTANTS:
    df_p = receptor_totals[receptor_totals["pollutant"] == pollutant]

    plt.figure(figsize=(10, 6))
    sns.lineplot(
        data=df_p,
        x="hour",
        y="total_concentration_ug_per_m3",
        hue="receptor_id",
        marker="o"
    )
    plt.title(f"Total Concentration at Receptors - {pollutant}")
    plt.xlabel("Hour")
    plt.ylabel("Concentration (μg/m³)")
    plt.grid(True)
    plt.legend(title="Receptor ID")
    plt.tight_layout()
    plot_path = f"for_sd/plots/receptor_hourly_concentration_{pollutant}.png"
    plt.savefig(plot_path, dpi=300)
    plt.close()
    print(f" [✓] Saved: {plot_path}")


'''''''''
''''''''''''''''
# === Save hourly outputs ===
for hour, df_hour in df.groupby("hour"):
    # Save CSV
    csv_path = f"gsa_hourly/hour_{hour:02d}_concentrations.csv"
    df_hour = df_hour.drop_duplicates(subset=["hour", "pollutant", "lane", "segment_index", "receptor_id", "x", "y"])

    # Compute total concentration per receptor and pollutant
    total_conc = (
        df_hour.groupby(["receptor_id", "pollutant"])["C_i_ug_per_m3"]
        .sum()
        .reset_index()
        .rename(columns={"C_i_ug_per_m3": "total_C_ug_per_m3"})
    )
# Merge into main df_hour for CSV saving
    df_hour = df_hour.merge(total_conc, on=["receptor_id", "pollutant"])
    csv_path = f"gsa_hourly/hour_{hour:02d}_concentrations.csv"
    df_hour.to_csv(csv_path, index=False)
    print(f" [✓] Saved: {csv_path}")

   '''''' 

    # Save Shapefile
    geometry = [Point(xy) for xy in zip(df_hour["x"], df_hour["y"])]
    gdf = gpd.GeoDataFrame(df_hour, geometry=geometry, crs="EPSG:32651")
    shp_path = f"gsa_hourly/hour_{hour:02d}_concentrations.shp"
    gdf.to_file(shp_path)
    print(f" [✓] Saved: {shp_path}")


# Compute global min/max for each pollutant
pollutant_vmin_vmax = {}
for pollutant in POLLUTANTS:
    df_p = df[df["pollutant"] == pollutant]
    vmin = df_p["C_i_ug_per_m3"].min()
    vmax = df_p["C_i_ug_per_m3"].max()
    pollutant_vmin_vmax[pollutant] = {"vmin": vmin, "vmax": vmax}

# === Plotting ===
for pollutant in POLLUTANTS:
    df_p = df[df["pollutant"] == pollutant]
    vmin = pollutant_vmin_vmax[pollutant]["vmin"]
    vmax = pollutant_vmin_vmax[pollutant]["vmax"]
    for hour, df_hour in df_p.groupby("hour"):
        plt.figure(figsize=(8, 6))
        
        for ridx, receptor in enumerate(receptors):
            subset = df_hour[df_hour["receptor_id"] == ridx]
            scatter = plt.scatter(
                subset["x"], subset["y"], 
                c=subset["C_i_ug_per_m3"], 
                cmap="hot", s=60, edgecolor="k",
                label=f"Contributors {ridx+1}",
                vmin=vmin, vmax=vmax  # consistent scale
            )
            plt.scatter(*receptor, c="blue", marker="x", label=f"Receptor {ridx + 1}")

        intersection_center = np.array([0, 0])
        plt.scatter(*intersection_center, c="black", marker="+", s=100, label="Intersection Center")
     # Add colorbar linked to the scatter plot
        cbar = plt.colorbar(scatter)
        cbar.set_label("Concentration (μg/m³)")

        #plt.colorbar(label="Concentration (μg/m³)")
        plt.title(f"GSA Concentrations for {pollutant} - Hour {hour}")
        plt.xlabel("x (m)")
        plt.ylabel("y (m)")
        plt.axis("equal")
        plt.legend()
        plt.grid(True)
        plt.tight_layout()
        plot_path = f"for_sd/plots/gsa_plot_{pollutant}_hour_{hour:02d}.png"
        plt.savefig(plot_path, dpi=300)
        plt.close()
        print(f" [✓] Plot saved: {plot_path}")

        
        '''''