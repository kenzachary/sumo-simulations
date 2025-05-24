import xml.etree.ElementTree as ET
import pandas as pd
import traci
from datetime import datetime

# Load the emissions XML file
file_path = "emissions.xml"  # Change if needed

try:
    tree = ET.parse(file_path)
    root = tree.getroot()
except FileNotFoundError:
    print(f"Error: File {file_path} not found.")
    exit()
except ET.ParseError:
    print(f"Error: {file_path} is empty or contains invalid XML.")
    exit()

# Initialize a list to store data
data = []

# Extract emissions data
for timestep in root.findall("timestep"):
    time = timestep.get("time")

    for vehicle in timestep.findall("vehicle"):
        veh_id = vehicle.get("id")
        co2 = vehicle.get("CO2")
        co = vehicle.get("CO")
        hc = vehicle.get("HC")
        nox = vehicle.get("NOx")
        pmx = vehicle.get("PMx")
        fuel = vehicle.get("fuel")
        speed = vehicle.get("speed")
       
        # Append data to list
        data.append([time, veh_id, co2, co, hc, nox, pmx, fuel, speed])

# Create a Pandas DataFrame
df = pd.DataFrame(data, columns=["Time (s)", "Vehicle ID", "CO2 (g)", "CO (g)", "HC (g)", "NOx (g)", "PMx (g)", "Fuel (L)", "Speed (m/s)"])

# Save to CSV
current_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
csv_filename = f"emissions_data_{current_time}.csv"
df.to_csv(csv_filename, index=False)
print(f"Emissions data saved to {csv_filename}")
