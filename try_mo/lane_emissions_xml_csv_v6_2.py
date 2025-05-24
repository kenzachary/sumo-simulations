import xml.etree.ElementTree as ET
import csv
from datetime import timedelta
from collections import defaultdict

# Input/output files
INPUT_XML = "lane_emissions-dir.xml"
OUTPUT_CSV = "lane_emissions_pivoted.csv"
CONVERSION_FACTOR = 0.27778  # g/km/h → µg/(m·s)

# Create a nested dictionary: data[(lane_id, pollutant)][interval_str] = value
data = defaultdict(lambda: defaultdict(float))

# Parse XML
tree = ET.parse(INPUT_XML)
root = tree.getroot()

for interval in root.findall("interval"):
    begin = float(interval.get("begin", 0))
    end = float(interval.get("end", 0))

    # Format interval as HH:MM to HH:MM
    begin_str = str(timedelta(seconds=int(begin)))[:-3].zfill(5)
    end_str = str(timedelta(seconds=int(end)))[:-3].zfill(5)
    interval_str = f"{begin_str} to {end_str}"

    for edge in interval.findall("edge"):
        for lane in edge.findall("lane"):
            lane_id = lane.get("id")

            # Extract normed values and convert
            pollutants = {
                "NOx": float(lane.get("NOx_normed", 0)) * CONVERSION_FACTOR,
                "CO": float(lane.get("CO_normed", 0)) * CONVERSION_FACTOR,
                "CO2": float(lane.get("CO2_normed", 0)) * CONVERSION_FACTOR,
                "PMx": float(lane.get("PMx_normed", 0)) * CONVERSION_FACTOR
            }

            # Breakdown calculations
            breakdown = {
                "NO": pollutants["NOx"] * 0.75,
                "NO2": pollutants["NOx"] * 0.25,
                "PM10": pollutants["PMx"] * 0.6,
                "PM2.5": pollutants["PMx"] * 0.4,
                "SO2": 0.0,
                "Ozone": 0.0
            }

            # Combine all pollutant values
            all_pollutants = {**pollutants, **breakdown}

            for pollutant, value in all_pollutants.items():
                data[(lane_id, pollutant)][interval_str] += value

# Determine all unique time intervals (sorted)
all_intervals = sorted({k for v in data.values() for k in v})

# Write pivoted CSV
with open(OUTPUT_CSV, "w", newline="") as csvfile:
    writer = csv.writer(csvfile)
    writer.writerow(["Lane", "Pollutant"] + all_intervals)

    for (lane, pollutant), interval_values in data.items():
        row = [lane, pollutant] + [f"{interval_values.get(t, 0):.2f}" for t in all_intervals]
        writer.writerow(row)

print(f"[DONE] Wrote pivoted emissions data to {OUTPUT_CSV}")
