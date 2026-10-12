# HarborFlow dataset dictionary

All identifiers and dates are strings. Dates use ISO `YYYY-MM-DD` format.
Numeric JSON values are JSON numbers; numeric CSV fields must be converted by
the program. Fields marked optional may be absent.

## `vessels/*.json`

- `vessel_id` (required): unique vessel identifier.
- `name` (required): display name used for user selection and sorting.
- `imo` (required): vessel IMO number used in inventory output.
- `capacity_teu` (required): integer carrying capacity.

## `manifests/*.json`

- `call_id` (required): links to `port_calls.csv` and incidents.
- `vessel_id` (required): links to a vessel.
- `shipment_ids` (required): ordered list of shipment identifiers.
- `event_codes` (required): chronological list used by Task 7.

## `shipments/*.json`

- `shipment_id`, `customer`, `destination`, `weight_kg`, and `priority`
  (required).
- `hazardous`, `temperature_controlled`, and `cargo_type` (optional).
- Missing booleans are treated as `false`; missing `cargo_type` is displayed as
  `NOT PROVIDED` where cargo type is printed.

## `incidents/*.json`

- `incident_id`, `call_id`, `title`, and `report` (required).

## `port_calls.csv`

- Header: `call_id,vessel_id,port_code,arrival_date`.
- Links calls to vessels, manifests, ports, and forecasts.

## `weather.csv`

- Header: `port_code,date,wind_kmh,precipitation_mm,wave_height_m`.
- A forecast matches a call by both `port_code` and date.

## Intentional test conditions

The supplied data includes one syntactically malformed vessel JSON file, one
missing shipment link (`SHP-1051`), one invalid call date, one non-numeric
weather value, and calls without forecasts. These are deliberate and must not
be corrected by students.
