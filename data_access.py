"""File loading, validation and safe writing for HarborFlow."""

import csv
import json
import math
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATASET = ROOT / "dataset"
EXPORTS = ROOT / "exports"


def parse_date(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}", value
    ):
        raise ValueError("Date must use YYYY-MM-DD.")
    return datetime.strptime(value, "%Y-%m-%d").date()


def display_date(value):
    months = (
        "January", "February", "March", "April",
        "May", "June", "July", "August",
        "September", "October", "November", "December",
    )
    return f"{value.day:02d} {months[value.month - 1]} {value.year}"


def load_json(path):
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle)


def number(value):
    if isinstance(value, bool) or not isinstance(
        value, (str, int, float)
    ):
        raise ValueError("Invalid number.")

    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError("Expected a finite non-negative number.")
    return result


def validate_record(record, kind):
    required = {
        "vessels": (
            "vessel_id", "name", "imo", "capacity_teu"
        ),
        "manifests": (
            "call_id", "vessel_id", "shipment_ids", "event_codes"
        ),
        "shipments": (
            "shipment_id", "customer", "destination",
            "weight_kg", "priority",
        ),
        "incidents": (
            "incident_id", "call_id", "title", "report"
        ),
    }[kind]

    if not isinstance(record, dict) or any(
        key not in record for key in required
    ):
        raise ValueError("Missing required fields or invalid record.")

    for key in required:
        value = record[key]

        if key in ("shipment_ids", "event_codes"):
            if not isinstance(value, list) or any(
                not isinstance(item, str) or not item
                for item in value
            ):
                raise ValueError(f"Invalid {key}.")

        elif key in ("weight_kg", "capacity_teu"):
            if isinstance(value, bool) or not isinstance(
                value, (int, float)
            ):
                raise ValueError(f"{key} must be a JSON number.")

            number(value)
            if key == "capacity_teu" and not isinstance(value, int):
                raise ValueError("Capacity must be an integer.")

        elif key == "imo":
            if not isinstance(value, str) or not value.strip():
                raise ValueError("Invalid IMO.")

        elif not isinstance(value, str) or (
            key != "report" and not value.strip()
        ):
            raise ValueError(f"Invalid {key}.")

    if kind == "shipments":
        for flag in ("hazardous", "temperature_controlled"):
            if flag in record and not isinstance(record[flag], bool):
                raise ValueError(f"Invalid {flag}.")

        if "cargo_type" in record and not isinstance(
            record["cargo_type"], str
        ):
            raise ValueError("Invalid cargo_type.")

    return record


def json_paths(directory, report=print):
    directory = Path(directory)
    try:
        if not directory.is_dir():
            raise FileNotFoundError(
                f"Directory not found: {directory.name}"
            )
        return sorted(directory.glob("*.json"))
    except OSError as error:
        report(
            f"Error - Cannot read {directory.name}: "
            f"{error.strerror or error}."
        )
        return []


def load_records(directory, kind, report=print):
    records = []
    skipped = 0

    for path in json_paths(directory, report):
        try:
            record = validate_record(load_json(path), kind)
        except (
            OSError, UnicodeError, json.JSONDecodeError, ValueError
        ) as error:
            report(f"Skipped {kind[:-1]} file {path.name}: {error}")
            skipped += 1
        else:
            records.append(record)

    return records, skipped


def load_vessels(directory=None, report=print):
    records, skipped = load_records(
        directory or DATASET / "vessels",
        "vessels",
        report,
    )
    records.sort(key=lambda item: item["name"].casefold())
    return records, skipped


def load_csv(path, required, report=print):
    path = Path(path)
    rows = []

    try:
        with path.open(
            encoding="utf-8-sig", newline=""
        ) as handle:
            reader = csv.DictReader(handle, strict=True)

            if reader.fieldnames is None or not set(
                required
            ).issubset(reader.fieldnames):
                raise ValueError("Missing required CSV columns.")

            for line, row in enumerate(reader, 2):
                if None in row or any(
                    row.get(key) is None or not row[key].strip()
                    for key in required
                ):
                    report(
                        f"Skipped {path.name} row {line}: "
                        "missing or extra fields."
                    )
                else:
                    rows.append(row)

    except (OSError, UnicodeError, csv.Error, ValueError) as error:
        report(f"Error - Cannot read {path.name}: {error}")

    return rows


def load_port_calls(report=print):
    rows = load_csv(
        DATASET / "port_calls.csv",
        ("call_id", "vessel_id", "port_code", "arrival_date"),
        report,
    )

    calls = []
    for row in rows:
        try:
            arrival = parse_date(row["arrival_date"])
        except ValueError:
            report(
                f"Skipped port call {row['call_id']}: "
                "invalid arrival date."
            )
        else:
            calls.append(dict(row, arrival=arrival))

    return calls


def find_manifest(call, report=print):
    records, _ = load_records(
        DATASET / "manifests", "manifests", report
    )

    return next(
        (
            item for item in records
            if item["call_id"].casefold()
            == call["call_id"].casefold()
            and item["vessel_id"] == call["vessel_id"]
        ),
        None,
    )


def atomic_write(path, writer):
    """Complete a temporary file before replacing an existing output."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=path.parent,
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            writer(handle)

        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def write_json(path, value):
    atomic_write(
        path,
        lambda handle: json.dump(
            value,
            handle,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        ),
    )