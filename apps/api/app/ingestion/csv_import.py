import csv
from io import StringIO

REQUIRED_COLUMNS = {
    "vehicle_id",
    "distance_km",
    "fuel_litres",
    "fuel_price_per_litre",
    "expected_litres_per_100km",
    "currency",
    "country_code",
}


def parse_fleet_csv(content: str) -> list[dict]:
    reader = csv.DictReader(StringIO(content))
    columns = set(reader.fieldnames or [])
    missing = REQUIRED_COLUMNS - columns
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")

    records = []
    for line_number, row in enumerate(reader, start=2):
        try:
            country = row["country_code"].strip().upper()
            currency = row["currency"].strip().upper()
            if len(country) != 2 or len(currency) != 3:
                raise ValueError("invalid country_code or currency")

            records.append({
                "vehicle_id": row["vehicle_id"].strip(),
                "distance_km": float(row["distance_km"]),
                "fuel_litres": float(row["fuel_litres"]),
                "fuel_price_per_litre": float(row["fuel_price_per_litre"]),
                "expected_litres_per_100km": float(row["expected_litres_per_100km"]),
                "currency": currency,
                "country_code": country,
            })
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid row {line_number}: {exc}") from exc

    return records
