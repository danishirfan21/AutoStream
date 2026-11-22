// Checks: data-integrity checks that make silent problems visible. Load as tblChecks. status is PASS or REVIEW.
// REVIEW means "look at it", not "something is broken".
let
    Recs = Table.ToRecords(SourceRecords),
    Raw = Raw_IngestionErrors,
    Rejected = F_Rejected,
    Ids = Table.Column(Findings, "finding_id"),
    Rows = {
        {"Source records with a timestamp that could not be parsed (ordering would treat them as missing)",
         List.Count(List.Select(Recs, (xr) => xr[source_timestamp_utc] <> "" and xr[ts] = null)), "0"},
        {"Source records with no source timestamp",
         List.Count(List.Select(Recs, (xr) => xr[source_timestamp_utc] = "")), "0 expected in the sample (information otherwise)"},
        {"Accepted source records whose VIN is not 17 characters",
         List.Count(List.Select(Recs, (xr) => Text.Length(xr[vin]) <> 17)), "0"},
        {"Rejection occurrences in the log minus occurrences accounted for by REJECTED_RECORD findings",
         Table.RowCount(Raw) - List.Sum(List.Combine({{0}, List.Transform(Table.Column(Rejected, "occurrences_canonical_sequence"), (x) => Number.FromText(x, "en-US"))})), "0"},
        {"Rejected records classified UNCLASSIFIED",
         List.Count(List.Select(Table.Column(Rejected, "rule_id"), (x) => x = "UNCLASSIFIED")), "0 (otherwise map the new error type)"},
        {"Duplicate finding_id values",
         List.Count(Ids) - List.Count(List.Distinct(Ids)), "0"},
        {"AMBIGUOUS_ORDER findings (records that cannot be ordered)",
         List.Count(List.Select(Ids, (x) => Text.StartsWith(x, "AMBIGUOUS_ORDER|"))), "0 expected in the sample"}
    },
    AsTable = Table.FromRows(Rows, {"check", "observed", "expected"}),
    WithStatus = Table.AddColumn(AsTable, "status",
        (r) => if r[observed] = 0 then "PASS" else "REVIEW", type text),
    Typed = Table.TransformColumnTypes(WithStatus, {{"check", type text}, {"observed", Int64.Type}, {"expected", type text}})
in
    Typed
