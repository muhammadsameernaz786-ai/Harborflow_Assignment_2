"""Shipment joins, business rules, customer exports and weather."""

import csv
import data_access as da

CATEGORIES = ("CONTROLLED", "COLD CHAIN", "EXPEDITE", "STANDARD")
PROFILE_FIELDS = (
    "customer",
    "shipment_count",
    "total_weight_kg",
    "express_count",
    "destinations",
)


def classify_shipment(shipment):
    # The first matching rule wins.
    if shipment.get("hazardous", False):
        return "CONTROLLED", "hazardous cargo"

    if shipment.get("temperature_controlled", False):
        return "COLD CHAIN", "temperature-controlled cargo"

    if shipment["priority"].upper() == "EXPRESS":
        return "EXPEDITE", "express service"

    if da.number(shipment["weight_kg"]) >= 5000:
        return "EXPEDITE", "weight at least 5000 kg"

    return "STANDARD", "standard handling"


def resolve_shipments(manifest, report=print):
    records, _ = da.load_records(
        da.DATASET / "shipments", "shipments", report
    )
    lookup = {
        item["shipment_id"]: item for item in records
    }

    return [
        (identifier, lookup.get(identifier))
        for identifier in manifest["shipment_ids"]
    ]


def upcoming_calls(calls, vessel_id, reference):
    return sorted(
        (
            call for call in calls
            if call["vessel_id"] == vessel_id
            and call["arrival"] >= reference
        ),
        key=lambda call: (call["arrival"], call["call_id"]),
    )


def customer_profile(shipments, name):
    matches = [
        item for item in shipments
        if item["customer"].casefold()
        == name.strip().casefold()
    ]

    if not matches:
        return None

    total_weight = sum(
        da.number(item["weight_kg"]) for item in matches
    )
    express_count = sum(
        item["priority"].upper() == "EXPRESS"
        for item in matches
    )
    destinations = sorted(
        {item["destination"] for item in matches}
    )

    return {
        "customer": matches[0]["customer"],
        "shipment_count": str(len(matches)),
        "total_weight_kg": f"{total_weight:.2f}",
        "express_count": str(express_count),
        "destinations": "|".join(destinations),
    }


def save_customer_profile(profile, path=None):
    path = path or da.EXPORTS / "customer-profiles.csv"
    rows = []

    if path.exists():
        with path.open(
            encoding="utf-8", newline=""
        ) as handle:
            reader = csv.DictReader(handle, strict=True)

            if reader.fieldnames != list(PROFILE_FIELDS):
                raise ValueError(
                    "Existing customer profile header is invalid."
                )

            for row in reader:
                if None in row or any(
                    row.get(key) is None
                    for key in PROFILE_FIELDS
                ):
                    raise ValueError(
                        "Existing customer profile row is invalid."
                    )
                rows.append(row)

    found = False
    updated = []

    for row in rows:
        if row["customer"].casefold() == profile["customer"].casefold():
            if not found:
                updated.append(profile)
                found = True
        else:
            updated.append(row)

    if not found:
        updated.append(profile)

    def writer(handle):
        output = csv.DictWriter(
            handle, fieldnames=PROFILE_FIELDS
        )
        output.writeheader()
        output.writerows(updated)

    da.atomic_write(path, writer)


def weather_recommendations(wind, rain, waves):
    recommendations = []

    if wind >= 45:
        recommendations.append("Suspend crane operations.")

    if waves >= 2.5:
        recommendations.append("Arrange tug assistance.")

    if rain >= 8 and wind < 45:
        recommendations.append("Prepare covered handling.")

    if wind < 45 and rain < 8 and waves < 2.5:
        recommendations.append("Normal operating plan.")

    return recommendations


def load_weather(report=print):
    rows = da.load_csv(
        da.DATASET / "weather.csv",
        (
            "port_code", "date", "wind_kmh",
            "precipitation_mm", "wave_height_m",
        ),
        report,
    )

    forecasts = {}

    for row in rows:
        try:
            date = da.parse_date(row["date"])
            wind = da.number(row["wind_kmh"])
            rain = da.number(row["precipitation_mm"])
            waves = da.number(row["wave_height_m"])
        except ValueError:
            report(
                f"Skipped weather row {row['port_code']} "
                f"{row['date']}: malformed forecast."
            )
        else:
            forecasts[(row["port_code"], date)] = (
                wind, rain, waves
            )

    return forecasts
