# Satellite_Transit_Finder
Tool calculates visible satellite transits in front of the sun for a given time window and location. Additionally uses object size data and telescope configuration to predict object size on image frame.

Requires python libraries skyfield, numpy, pillow

## Data Sources & Attributions

This project fetches and combines orbital and physical data from the following public sources:

### 1. Orbital Elements (TLEs)
* **Source:** [CelesTrak](https://celestrak.org) (by Dr. T.S. Kelso)
* **Dataset:** Real-time General Perturbation (GP) Element Sets (TLEs) for satellite groups.
* **Citation/Attribution:** > Kelso, T.S. *CelesTrak SatCat and Orbit Determination Data.* Retrieved from https://celestrak.org.

### 2. Physical Dimensions & Sizing (GCAT)
* **Source:** General Catalog of Artificial Space Objects (GCAT) (by Dr. Jonathan C. McDowell)
* **Dataset:** Satellite Catalog (satcat.tsv)
* **Citation/Attribution:**
  > McDowell, Jonathan C., 2020. General Catalog of Artificial Space Objects, Release 1.8.1, https://planet4589.org/space/gcat
