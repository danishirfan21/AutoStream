// VinSourceLatest: one row per (VIN, source) with the LATEST record by source timestamp, for XLOOKUP reconciliation.
// Load as an Excel Table named tblLatest. key = vin & "|" & source_name.
// status: OK                    = the latest timestamp identifies the record (or ties agree on every compared value)
//         AMBIGUOUS_TIE         = records share the greatest timestamp and disagree: values are left BLANK, none chosen
//         UNORDERABLE_NO_TS     = 2+ records and one lacks a source timestamp: values are left BLANK
// A single record without a timestamp is usable (status OK, latest_ts empty).
let
    Recs = Table.ToRecords(SourceRecords),
    Pairs = List.Distinct(List.Transform(Recs, (xr) => {xr[vin], xr[source_name]})),
    Compared = Lib[Attributes] & {"mileage"},
    Rows = List.Transform(Pairs, (xk) =>
        let
            pr = List.Select(Recs, (xr) => xr[vin] = xk{0} and xr[source_name] = xk{1}),
            groups = Lib[TsGroups](pr),
            lastGrp = if groups = null then null else List.Last(groups),
            bad = if lastGrp = null then {} else Lib[DifferingFields](lastGrp, Compared),
            xStatus = if groups = null then "UNORDERABLE_NO_TS" else if not List.IsEmpty(bad) then "AMBIGUOUS_TIE" else "OK",
            xOk = xStatus = "OK",
            First = (xf as text) as nullable text =>
                if not xOk then null
                else List.First(List.RemoveNulls(List.Transform(lastGrp, (xr) => Record.Field(xr, xf))), null),
            xMil = if not xOk then null else List.First(List.RemoveNulls(List.Transform(lastGrp, (xr) => xr[mileage])), null)
        in
            [key = xk{0} & "|" & xk{1},
             vin = xk{0},
             source_name = xk{1},
             record_count = List.Count(pr),
             status = xStatus,
             latest_source_record_id = if xOk then lastGrp{0}[source_record_id] else null,
             latest_ts = if xOk then lastGrp{0}[source_timestamp_utc] else null,
             year = First("year"),
             make = First("make"),
             model = First("model"),
             trim = First("trim"),
             mileage = xMil]),
    Result = Table.FromRecords(Rows)
in
    Result
