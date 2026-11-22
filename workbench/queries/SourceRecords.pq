// SourceRecords: one row per accepted source record, original evidence kept, plus parsed fields.
// Kept as-is from Raw_SourceRecords: vin (TEXT), source_name, source_record_id, source_timestamp_utc (original text),
// payload_hash, raw_payload_json (verbatim). A missing source timestamp is represented as "" (never replaced by a
// date). Added: ts (the same instant as a datetimezone in UTC, used ONLY for ordering; null when missing or
// unparseable), the four compared attributes (trimmed text or null), mileage (whole number or null).
// An unparseable timestamp gives ts = null and is counted by the Checks query (it is not guessed or repaired).
let
    Raw = Raw_SourceRecords,
    TsText = Table.TransformColumns(Raw, {{"source_timestamp_utc", (x) => if x = null then "" else x, type text}}),
    WithPayload = Table.AddColumn(TsText, "payload",
        (r) => Json.Document(Text.ToBinary(r[raw_payload_json], TextEncoding.Utf8)), type record),
    WithTs = Table.AddColumn(WithPayload, "ts",
        (r) => if r[source_timestamp_utc] = "" then null
               else try DateTimeZone.ToUtc(DateTimeZone.FromText(r[source_timestamp_utc])) otherwise null,
        type nullable datetimezone),
    WithAttrs = List.Accumulate(Lib[Attributes], WithTs,
        (state, f) => Table.AddColumn(state, f, (r) => Lib[Field](r[payload], r[source_name], f), type nullable text)),
    WithMileage = Table.AddColumn(WithAttrs, "mileage",
        (r) => Lib[ParseMileage](Lib[Field](r[payload], r[source_name], "mileage")), type nullable number),
    Result = Table.RemoveColumns(WithMileage, {"payload"})
in
    Result
