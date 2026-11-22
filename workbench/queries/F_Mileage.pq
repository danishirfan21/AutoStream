// F_Mileage: MILEAGE_REGRESSION findings (+ ordering-ambiguity candidates). Returns a record:
//   Findings   = table of finding rows
//   Candidates = table of ambiguity candidates (merged into AMBIGUOUS_ORDER findings by F_Ambiguous)
// Rule (same as reference_findings.py mileage_regressions): per VIN, across all sources, order records by SOURCE
// timestamp only. Records that share a timestamp form one group. If a group's mileages disagree, the group is
// ambiguous: a candidate is recorded and the previous value is dropped (never compared across it). If 2+ records
// exist and any lacks a source timestamp, ordering is impossible: candidate, no comparison. A later mileage lower
// than the previous one is an anomaly flag, not proof of corruption.
let
    Recs = Table.ToRecords(SourceRecords),
    Vins = Lib[SortOrd](List.Distinct(List.Transform(Recs, (xr) => xr[vin]))),

    MkRow = (xVin as text, xPrev as record, xCur as record) as record =>
        Lib[Blank]([
            finding_id = "MILEAGE_REGRESSION|" & xVin & "|" & xCur[source_name] & "|" & xCur[source_record_id] & "|" & xCur[source_timestamp_utc],
            issue_type = "MILEAGE_REGRESSION",
            rule_id = "MILEAGE_NON_DECREASING",
            evidence_class = "SOURCE_DISCREPANCY",
            assessment = "SUSPICIOUS_REQUIRES_INVESTIGATION",
            confirmed_invalid_input = "undetermined",
            counts_as_actionable = "yes",
            vin = xVin,
            field = "mileage",
            source_a = xPrev[rec][source_name],
            source_record_id_a = xPrev[rec][source_record_id],
            timestamp_a = xPrev[rec][source_timestamp_utc],
            value_a = Text.From(xPrev[m], "en-US"),
            source_b = xCur[source_name],
            source_record_id_b = xCur[source_record_id],
            timestamp_b = xCur[source_timestamp_utc],
            value_b = Text.From(xCur[mileage], "en-US"),
            derived_from = "FIXTURE_CONTENT",
            fixture_evidence = "Mileage decreased " & Text.From(xPrev[m], "en-US") & " -> " & Text.From(xCur[mileage], "en-US")
                & " between consecutive observations ordered by source timestamp (" & xPrev[rec][source_timestamp_utc]
                & " -> " & xCur[source_timestamp_utc] & "). Anomaly flag only; not proof of corruption."
        ]),

    PerVin = (xVin as text) as record =>
        let
            vr = List.Select(Recs, (xr) => xr[vin] = xVin),
            groups = Lib[TsGroups](vr),
            Step = (st as record, g as list) as record =>
                let
                    vals = List.RemoveNulls(List.Transform(g, (xr) => xr[mileage])),
                    cur = List.First(List.Select(g, (xr) => xr[mileage] <> null), null)
                in
                    if List.Count(List.Distinct(vals)) > 1 then
                        [Prev = null, Findings = st[Findings],
                         Amb = st[Amb] & {Lib[Amb](xVin, g, g{0}[source_timestamp_utc], {"mileage"})}]
                    else if List.IsEmpty(vals) then st
                    else
                        [Prev = [rec = cur, m = cur[mileage]],
                         Findings = if st[Prev] <> null and cur[mileage] < st[Prev][m]
                                    then st[Findings] & {MkRow(xVin, st[Prev], cur)} else st[Findings],
                         Amb = st[Amb]]
        in
            if groups = null then
                [Findings = {}, Amb = {Lib[Amb](xVin, List.Select(vr, (xr) => xr[ts] = null), "", {"mileage"})}]
            else
                let acc = List.Accumulate(groups, [Prev = null, Findings = {}, Amb = {}], Step)
                in [Findings = acc[Findings], Amb = acc[Amb]],

    Results = List.Transform(Vins, PerVin),
    AllFindings = List.Combine(List.Transform(Results, (x) => x[Findings])),
    AllAmb = List.Combine(List.Transform(Results, (x) => x[Amb])),
    Out = [Findings = Lib[ToTable](AllFindings), Candidates = Lib[CandTable](AllAmb)]
in
    Out
