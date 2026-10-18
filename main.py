"""HarborFlow Port Intelligence Console."""

import calendar
import csv
import data_access as da
import operations as op
import text_tools as text

MENU = """HARBORFLOW PORT INTELLIGENCE
1. List registered vessels
2. Inspect a vessel manifest
3. Identify priority cargo
4. Export a customer operations profile
5. Find port calls by month
6. Sanitize an incident report
7. Analyze the longest stable event sequence
8. Assess weather risk for upcoming calls
9. Search incident reports
10. Close console"""


def list_vessels():
    vessels, skipped = da.load_vessels()

    print("Registered HarborFlow vessels:")
    for vessel in vessels:
        capacity = int(da.number(vessel["capacity_teu"]))
        print(
            f"- {vessel['name']} | IMO {vessel['imo']} "
            f"| {capacity:,} TEU"
        )

    print(f"Skipped vessel files: {skipped}")
    return vessels


def prompt_date():
    date = None

    while date is None:
        raw = input("Reference date (YYYY-MM-DD): ").strip()
        try:
            date = da.parse_date(raw)
        except ValueError:
            print("Error - Date must use YYYY-MM-DD.")

    return date


def select_vessel(vessels):
    name = input("Vessel name: ").strip().casefold()
    vessel = next(
        (
            item for item in vessels
            if item["name"].casefold() == name
        ),
        None,
    )

    if vessel is None:
        print("Vessel not found.")

    return vessel


def select_call():
    identifier = input("Call ID: ").strip().casefold()
    call = next(
        (
            item for item in da.load_port_calls()
            if item["call_id"].casefold() == identifier
        ),
        None,
    )

    if call is None:
        print("Port call not found.")

    return call


def get_manifest(call):
    manifest = da.find_manifest(call)

    if manifest is None:
        print("Manifest unavailable.")

    return manifest


def inspect_manifest():
    vessel = select_vessel(list_vessels())
    if vessel is None:
        return

    reference = prompt_date()
    calls = op.upcoming_calls(
        da.load_port_calls(), vessel["vessel_id"], reference
    )

    if not calls:
        print("No upcoming port calls found.")
        return

    call = calls[0]
    manifest = get_manifest(call)
    if manifest is None:
        return

    print(
        f"Manifest for {vessel['name']} "
        f"| Call {call['call_id']} "
        f"| {da.display_date(call['arrival'])}"
    )

    weight = 0.0
    missing = 0

    for position, (identifier, shipment) in enumerate(
        op.resolve_shipments(manifest), 1
    ):
        if shipment is None:
            print(f"{position}. {identifier} | MISSING RECORD")
            missing += 1
        else:
            shipment_weight = da.number(shipment["weight_kg"])
            weight += shipment_weight
            cargo_type = shipment.get(
                "cargo_type", "NOT PROVIDED"
            )

            print(
                f"{position}. {identifier} "
                f"| {shipment['customer']} "
                f"| {shipment_weight:.1f} kg "
                f"| {cargo_type}"
            )

    print(f"Declared shipments: {len(manifest['shipment_ids'])}")
    print(f"Resolved weight: {weight:.2f} kg")
    print(f"Missing shipment records: {missing}")


def priority_cargo():
    call = select_call()
    if call is None:
        return

    manifest = get_manifest(call)
    if manifest is None:
        return

    totals = dict.fromkeys(op.CATEGORIES, 0)

    for identifier, shipment in op.resolve_shipments(manifest):
        if shipment is None:
            print(f"{identifier} | MISSING RECORD")
        else:
            category, reason = op.classify_shipment(shipment)
            totals[category] += 1
            print(f"{identifier} | {category} | {reason}")

    print(
        "Category totals: "
        + ", ".join(
            f"{category}={count}"
            for category, count in totals.items()
        )
    )


def export_customer():
    name = input("Customer name: ").strip()
    shipments, _ = da.load_records(
        da.DATASET / "shipments", "shipments"
    )
    profile = op.customer_profile(shipments, name)

    if profile is None:
        print("Customer not found.")
        return

    try:
        op.save_customer_profile(profile)
    except (OSError, UnicodeError, csv.Error, ValueError) as error:
        print(f"Error - Cannot update customer profiles: {error}")
    else:
        print(
            "Customer profile updated: "
            "exports/customer-profiles.csv"
        )


def calls_by_month():
    month = None

    while month is None:
        try:
            candidate = int(input("Month (1-12): "))
            if not 1 <= candidate <= 12:
                raise ValueError("Out of range.")
        except ValueError:
            print("Error - Enter a month from 1 to 12.")
        else:
            month = candidate

    vessels, _ = da.load_vessels()
    names = {
        item["vessel_id"]: item["name"]
        for item in vessels
    }

    calls = []

    for call in da.load_port_calls():
        if call["vessel_id"] not in names:
            print(
                f"Skipped port call {call['call_id']}: "
                "unknown vessel_id."
            )
        elif call["arrival"].month == month:
            calls.append(call)

    if not calls:
        print("No port calls found.")
        return

    print(f"Port calls in {calendar.month_name[month]}:")

    calls.sort(
        key=lambda item: (
            item["arrival"],
            names[item["vessel_id"]].casefold(),
            item["call_id"],
        )
    )

    for call in calls:
        print(
            f"- {da.display_date(call['arrival'])} "
            f"| {names[call['vessel_id']]} "
            f"| {call['port_code']} "
            f"| {call['call_id']}"
        )


def sanitize_incident():
    incidents, _ = da.load_records(
        da.DATASET / "incidents", "incidents"
    )
    incidents.sort(
        key=lambda item: (
            item["title"].casefold(),
            item["incident_id"],
        )
    )

    if not incidents:
        print("No incidents found.")
        return

    for position, incident in enumerate(incidents, 1):
        print(f"{position}. {incident['title']}")

    selected = None

    while selected is None:
        try:
            candidate = int(input("Incident number: "))
            if not 1 <= candidate <= len(incidents):
                raise ValueError("Out of range.")
        except ValueError:
            print("Error - Select a listed incident.")
        else:
            selected = incidents[candidate - 1]

    sanitized, changed = text.sanitize_report(
        selected["report"]
    )

    if not changed:
        print("Incident contains no share-sensitive identifiers.")
        return

    identifier = selected["incident_id"]

    if (
        "/" in identifier
        or "\\" in identifier
        or identifier in (".", "..")
    ):
        print("Error - Incident ID cannot be used as a filename.")
        return

    path = (
        da.EXPORTS / "sanitized"
        / f"{identifier}-sanitized.txt"
    )

    try:
        da.atomic_write(
            path, lambda handle: handle.write(sanitized)
        )
    except OSError as error:
        print(f"Error - Cannot save sanitized incident: {error}")
    else:
        print(
        "Incident sanitized: "
        f"exports/sanitized/{identifier}-sanitized.txt"
    )


def stable_sequence():
    call = select_call()
    if call is None:
        return

    manifest = get_manifest(call)
    if manifest is None:
        return

    events = manifest["event_codes"]
    sequence = text.longest_stable_sequence(events)

    print("Event codes: " + ",".join(events))
    print(f"Longest stable sequence length: {len(sequence)}")
    print("Sequence: " + " -> ".join(sequence))


def weather_risk():
    vessels, _ = da.load_vessels()
    vessel = select_vessel(vessels)
    if vessel is None:
        return

    reference = prompt_date()
    calls = op.upcoming_calls(
        da.load_port_calls(), vessel["vessel_id"], reference
    )

    if not calls:
        print("No upcoming port calls found.")
        return

    forecasts = op.load_weather()

    for call in calls:
        print(
            f"{vessel['name']} | {call['port_code']} "
            f"| {da.display_date(call['arrival'])}"
        )

        forecast = forecasts.get(
            (call["port_code"], call["arrival"])
        )

        if forecast is None:
            print("Forecast unavailable")
        else:
            wind, rain, waves = forecast
            print(
                f"Wind: {wind:.1f} km/h "
                f"| Rain: {rain:.1f} mm "
                f"| Waves: {waves:.1f} m"
            )
            print(
                "Recommendation: "
                + " ".join(
                    op.weather_recommendations(
                        wind, rain, waves
                    )
                )
            )


def search_incidents():
    query = input("Search incident reports: ")

    try:
        cache = text.load_incident_index()
    except (OSError, UnicodeError) as error:
        print(f"Error - Cannot prepare incident index: {error}")
        return

    matches = text.search_index(cache, query)
    print(f"Matches for '{query}':")

    if not matches:
        print("No matches found.")

    for identifier, score, title in matches:
        print(f"- {identifier} | score {score} | {title}")


def main():
    services = {
        1: list_vessels,
        2: inspect_manifest,
        3: priority_cargo,
        4: export_customer,
        5: calls_by_month,
        6: sanitize_incident,
        7: stable_sequence,
        8: weather_risk,
        9: search_incidents,
    }

    running = True

    while running:
        print(MENU)

        try:
            service = int(input("Select service: "))
            if not 1 <= service <= 10:
                raise ValueError("Out of range.")
        except ValueError:
            print("Error - Select a service from 1 to 10.")
        else:
            if service == 10:
                running = False
                print(
                    "Console closed. HarborFlow operational "
                    "data remains safe."
                )
            else:
                services[service]()


if __name__ == "__main__":
    main()