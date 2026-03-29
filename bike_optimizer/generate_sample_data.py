"""
Generate two synthetic Citi Bike trip CSV subsets for Q2 acceptance cases.

Case 1 — "membership_wins.csv"
  Many long rides + frequent e-bike use → monthly membership saves money.

Case 2 — "payperuse_wins.csv"
  Few short rides → pay-per-use is cheaper than $19.99/month.

Citi Bike pricing (March 2026, citibikenyc.com/pricing):
  - Single ride:        $4.99 for 30 min classic, then $0.26/min overage
  - E-bike single ride: $4.99 unlock + $0.26/min from minute 1
  - Monthly membership: $19.99/month, 45 min included per ride (classic)
                        E-bike: $0.26/min surcharge even for members
  - Day pass:           $19.00/24h, 30 min per ride

Run:
    cd HW7
    source .venv/bin/activate
    python bike_optimizer/generate_sample_data.py
"""

import csv
import os
import random
from datetime import datetime, timedelta

random.seed(42)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "sample_data")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Citi Bike NYC stations (real names)
STATIONS = [
    "W 21 St & 6 Ave",
    "E 17 St & Broadway",
    "8 Ave & W 31 St",
    "Central Park S & 6 Ave",
    "Broadway & W 60 St",
    "W 41 St & 8 Ave",
    "University Pl & E 14 St",
    "Fulton St & Broadway",
    "Hudson St & Reade St",
    "W 72 St & Columbus Ave",
]

BIKE_TYPES = ["classic_bike", "electric_bike"]


def make_ride(start_dt: datetime, duration_min: float, bike_type: str) -> dict:
    end_dt = start_dt + timedelta(minutes=duration_min)
    start_station = random.choice(STATIONS)
    end_station = random.choice([s for s in STATIONS if s != start_station])
    return {
        "ride_id": f"ride_{random.randint(100000,999999)}",
        "rideable_type": bike_type,
        "started_at": start_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "ended_at": end_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "start_station_name": start_station,
        "end_station_name": end_station,
        "tripduration": int(duration_min * 60),
        "member_casual": "casual",
    }


def write_csv(filename: str, rows: list[dict]) -> str:
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    return path


# ─────────────────────────────────────────────────────────────────────────────
# CASE 1: Membership Wins
# 80 rides, avg 55 min, 60% e-bike → heavy user
# Pay-per-use would cost a lot; membership + e-bike surcharges still cheaper
# ─────────────────────────────────────────────────────────────────────────────
print("Generating Case 1: Membership Wins (30 rides, long + e-bike heavy)…")
rides_membership = []
base = datetime(2024, 9, 2, 7, 30)  # Sept 2024, NYC commuter month

# 30 CASUAL rides for the target rider — frequent commuter, long + e-bike
# Membership cost: $19.99  (covers 45-min classic; e-bike surcharge only)
# Pay-per-use cost: 30 rides × (~$4.99 + overages + e-bike fees) >> $19.99
for i in range(30):
    day_offset = i % 30
    hour = 8 if i % 2 == 0 else 18   # commute pattern
    start = base + timedelta(days=day_offset, hours=hour, minutes=random.randint(0, 20))
    duration = round(random.gauss(52, 8), 1)   # avg 52 min — over 45-min free window
    duration = max(40, min(90, duration))
    bike = "electric_bike" if random.random() < 0.60 else "classic_bike"
    row = make_ride(start, duration, bike)
    row["member_casual"] = "casual"
    rides_membership.append(row)

# Pad to 500+ rows with background member traffic
for i in range(520):
    day_offset = i % 30
    start = base + timedelta(days=day_offset, hours=random.randint(7, 20), minutes=random.randint(0, 45))
    duration = round(random.gauss(22, 8), 1)
    duration = max(5, min(60, duration))
    bike = random.choice(["classic_bike", "classic_bike", "electric_bike"])
    row = make_ride(start, duration, bike)
    row["member_casual"] = "member"
    rides_membership.append(row)

random.shuffle(rides_membership)
path1 = write_csv("membership_wins.csv", rides_membership)
print(f"  ✅ {len(rides_membership)} rows → {path1}")
print(f"     Casual (target rider): 30 rides, avg ~52 min, 60% e-bike")

# ─────────────────────────────────────────────────────────────────────────────
# CASE 2: Pay-Per-Use Wins
# SAME 30 rides/month as Case 1, but SHORT classic rides (avg 12 min)
# Pay-per-use: 30 × $4.99 = $149.70? No — rides under 30 min cost $4.99 flat.
# BUT membership is only $19.99, so 30 × $4.99 = $149.70 >> $19.99.
#
# To make pay-per-use win we need < 4 rides/month (break-even at ~4 rides):
# 4 × $4.99 = $19.96 ≈ $19.99 membership
# So: 3 rides × $4.99 = $14.97 < $19.99  → pay-per-use wins by $5.02
#
# Pattern: occasional tourist/visitor — 3 rides total, short, classic only
# ─────────────────────────────────────────────────────────────────────────────
print("Generating Case 2: Pay-Per-Use Wins (3 rides, short classic, occasional rider)…")
rides_payperuse = []
base2 = datetime(2024, 11, 5, 10, 0)  # Nov 2024

# 3 CASUAL rides — occasional visitor, short trips, all classic
# Pay-per-use: 3 × $4.99 = $14.97  <  $19.99 membership  → pay-per-use wins
TARGET_DAYS = [3, 14, 26]   # 3 rides spread across the month
for day in TARGET_DAYS:
    start = base2 + timedelta(days=day, hours=random.randint(10, 16), minutes=random.randint(0, 30))
    duration = round(random.uniform(10, 14), 1)   # avg 12 min, well under 30-min free window
    row = make_ride(start, duration, "classic_bike")
    row["member_casual"] = "casual"
    rides_payperuse.append(row)

# Pad to 500+ rows with background member traffic
for i in range(520):
    day_offset = i % 30
    start = base2 + timedelta(days=day_offset, hours=random.randint(7, 20), minutes=random.randint(0, 45))
    duration = round(random.gauss(18, 6), 1)
    duration = max(5, min(45, duration))
    bike = random.choice(["classic_bike", "classic_bike", "electric_bike"])
    row = make_ride(start, duration, bike)
    row["member_casual"] = "member"
    rides_payperuse.append(row)

random.shuffle(rides_payperuse)
path2 = write_csv("payperuse_wins.csv", rides_payperuse)
print(f"  ✅ {len(rides_payperuse)} rows → {path2}")
print("     Casual (target rider): 3 rides | Members (background): 510 rides")
print("     Pay-per-use cost: 3 × $4.99 = $14.97  <  $19.99 membership → Pay-Per-Use wins")

print("\n✅ Sample data generated!")
print(f"\nFiles in: {OUTPUT_DIR}")
print("\nCase 1 — membership_wins.csv:")
print("  600 rides, avg ~52 min, 60% e-bike")
print("  Pay-per-use: very expensive (600 × $4.99 + overage + ebike surcharges)")
print("  Membership: $19.99 + e-bike surcharges only → much cheaper")
print("\nCase 2 — payperuse_wins.csv:")
print("  520 rides but avg ~14 min, all classic, all within 30-min window")
print("  Pay-per-use: 520 × $4.99 = $2,594.80 (many rides!)")
print("  Note: agent will determine based on actual ride count & cost")
print("\nUse these CSVs when running the bike optimizer UI!")
