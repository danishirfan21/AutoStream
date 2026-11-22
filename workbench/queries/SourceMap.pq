// The ONLY place coupled to feed formats. Mirrors SOURCES in reference_findings.py (a test compares them).
// Maps each source_name to the payload field that holds each logical value. An unknown source_name raises an error
// downstream (Record.Field) instead of being skipped.
[
    dealer_csv = [
        vin = "vin", timestamp = "updated_at", year = "year", make = "make", model = "model", trim = "trim",
        mileage = "mileage", price = "price", record_key = "vin"
    ],
    marketplace_json = [
        vin = "vehicle_vin", timestamp = "updated", year = "model_year", make = "brand", model = "vehicle_model",
        trim = "variant", mileage = "odometer_miles", price = "asking_price", record_key = "listing_id"
    ]
]
