# app.py
from flask import Flask, request, jsonify
import xml.etree.ElementTree as ET
import numpy as np

app = Flask(__name__)

# Screening parameters
U_wc = 1.0            # Worst-case wind speed at 10 m (m/s) :contentReference[oaicite:12]{index=12}
H_wc = 50.0           # Worst-case cloud depth (m) :contentReference[oaicite:13]{index=13}

POLLUTANTS = ["CO", "CO2", "NOx", "PMx"]

@app.route("/compute", methods=["POST"])
def compute_screening():
    """
    Endpoint to compute gross screening concentrations.
    Expects:
        - 'emissions_file': uploaded XML with per-lane pollutant_normed values (g/km/h).
        - 'distance': downwind distance x (meters).
    Returns:
        JSON dict with { pollutant: { 'Q_kg_per_s': ..., 'C_wc_ug_per_m3': ... } }.
    """
    file = request.files.get("emissions_file")
    x = float(request.form.get("distance", 100.0))  # Default 100 m if not provided

    if not file:
        return jsonify({"error": "No emissions file provided."}), 400

    # Parse XML
    tree = ET.parse(file)
    root = tree.getroot()

    # Initialize total emission rates per pollutant (kg/s)
    total_emissions = {pollutant: 0.0 for pollutant in POLLUTANTS}

    # Loop through each 'interval' → 'edge' → 'lane' structure
    for interval in root.findall("interval"):
        for edge in interval.findall("edge"):
            for lane in edge.findall("lane"):
                # Extract lane length L (if not directly in XML, replace with known mapping)
                L = float(lane.get("length", 0))  # [m] :contentReference[oaicite:14]{index=14}
                if L <= 0:
                    continue  # Skip lanes without length info

                # Number of segments (must match frontend logic if needed)
                N_seg = 10

                # For each pollutant, convert and accumulate Q
                for pollutant in POLLUTANTS:
                    E_normed = float(lane.get(f"{pollutant}_normed", 0))  # [g/km/h] :contentReference[oaicite:15]{index=15}
                    # Convert to kg/s per meter
                    emission_per_m = E_normed * 1e-6 / 3600  # :contentReference[oaicite:16]{index=16}
                    # Each segment length Δx
                    delta_x = L / N_seg
                    # Emission from the segment (kg/s)
                    Q_seg = emission_per_m * delta_x  # :contentReference[oaicite:17]{index=17}
                    # Add to total for pollutant
                    total_emissions[pollutant] += Q_seg * N_seg  # Summing across all segments :contentReference[oaicite:18]{index=18}

    # Compute screening concentrations
    results = {}
    for pollutant, Q in total_emissions.items():
        # Cloud width: W_wc = 0.1 * x for conservative lateral spread :contentReference[oaicite:19]{index=19}
        W_wc = 0.1 * x
        # Gross screening formula: C_wc [µg/m³]
        if U_wc * H_wc * W_wc > 0:
            C_wc = (10.0 * Q) / (U_wc * H_wc * W_wc)  # :contentReference[oaicite:20]{index=20}
            C_wc *= 1e6  # Convert from kg/m³ to µg/m³ (1 kg/m³ = 1e9 µg/m³; factor 10 already accounted) :contentReference[oaicite:21]{index=21}
        else:
            C_wc = 0.0

        results[pollutant] = {
            "Q_kg_per_s": Q,
            "C_wc_ug_per_m3": C_wc
        }

    return jsonify(results)

if __name__ == "__main__":
    app.run(debug=True)


