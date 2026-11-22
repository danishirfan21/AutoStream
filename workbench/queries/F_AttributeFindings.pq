// F_AttributeFindings: ATTR_CONFLICT and ATTR_DRIFT findings (+ ordering-ambiguity candidates). Returns a record:
//   Conflicts, Drifts = tables of finding rows;  Candidates = ambiguity candidates (see F_Ambiguous).
// Same rules as reference_findings.py attribute_findings. Attributes compared: year, make, model, trim (trimmed,
// case-sensitive). Ordering uses the SOURCE timestamp only; ties that disagree and unorderable scopes become
// ambiguity candidates, never a guess.
//  * ATTR_CONFLICT: the latest record of each source for one VIN (greatest source timestamp) disagree on a field.
//  * ATTR_DRIFT: successive versions of ONE source record (same source + source_record_id) change a field.
let
    Recs = Table.ToRecords(SourceRecords),
    Attrs = Lib[Attributes],
    Vins = Lib[SortOrd](List.Distinct(List.Transform(Recs, (xr) => xr[vin]))),

    ConflictRow = (xVin as text, xf as text, a as record, b as record) as record =>
        Lib[Blank]([
            finding_id = "ATTR_CONFLICT|" & xVin & "|" & xf & "|" & a[src] & "~" & b[src],
            issue_type = "ATTR_CONFLICT",
            rule_id = "ATTR_CROSS_SOURCE_AGREEMENT",
            evidence_class = "SOURCE_DISCREPANCY",
            assessment = "SUSPICIOUS_REQUIRES_INVESTIGATION",
            confirmed_invalid_input = "undetermined",
            counts_as_actionable = "yes",
            vin = xVin,
            field = xf,
            source_a = a[src],
            source_record_id_a = a[rec][source_record_id],
            timestamp_a = a[rec][source_timestamp_utc],
            value_a = Record.Field(a[rec], xf),
            source_b = b[src],
            source_record_id_b = b[rec][source_record_id],
            timestamp_b = b[rec][source_timestamp_utc],
            value_b = Record.Field(b[rec], xf),
            derived_from = "FIXTURE_CONTENT",
            fixture_evidence = "Latest record per source by source timestamp disagrees on " & xf & ": "
                & Record.Field(a[rec], xf) & " vs " & Record.Field(b[rec], xf) & "."
                & (if a[flag] or b[flag] then " A source timestamp is missing on a single record (flagged)." else "")
        ]),

    DriftRow = (xVin as text, xf as text, xSrc as text, xRid as text, ka as record, kb as record) as record =>
        Lib[Blank]([
            finding_id = "ATTR_DRIFT|" & xVin & "|" & xf & "|" & xSrc & "|" & kb[rec][source_timestamp_utc],
            issue_type = "ATTR_DRIFT",
            rule_id = "ATTR_SAME_SOURCE_STABILITY",
            evidence_class = "SOURCE_DISCREPANCY",
            assessment = "OBSERVED_CHANGE_UNVERIFIED",
            confirmed_invalid_input = "undetermined",
            counts_as_actionable = "yes",
            vin = xVin,
            field = xf,
            source_a = xSrc,
            source_record_id_a = xRid,
            timestamp_a = ka[rec][source_timestamp_utc],
            value_a = ka[val],
            source_b = xSrc,
            source_record_id_b = xRid,
            timestamp_b = kb[rec][source_timestamp_utc],
            value_b = kb[val],
            derived_from = "FIXTURE_CONTENT",
            fixture_evidence = "Same source record changed " & xf & ": " & ka[val] & " -> " & kb[val] & " ("
                & ka[rec][source_timestamp_utc] & " -> " & kb[rec][source_timestamp_utc]
                & "). May be a correction; cause unknown."
        ]),

    PerVin = (xVin as text) as record =>
        let
            vr = List.Select(Recs, (xr) => xr[vin] = xVin),
            srcs = Lib[SortOrd](List.Distinct(List.Transform(vr, (xr) => xr[source_name]))),

            // ---- latest record per source
            LatestOne = (xSrc as text) as record =>
                let
                    sr = List.Select(vr, (xr) => xr[source_name] = xSrc),
                    groups = Lib[TsGroups](sr)
                in
                    if groups = null then
                        [Entries = {},
                         Amb = {Lib[Amb](xVin, List.Select(sr, (xr) => xr[ts] = null), "", Attrs)}]
                    else
                        let
                            lastGrp = List.Last(groups),
                            bad = Lib[DifferingFields](lastGrp, Attrs),
                            ents = List.RemoveNulls(List.Transform(Attrs, (xf) =>
                                if List.Contains(bad, xf) then null
                                else
                                    let xrec = List.First(List.Select(lastGrp, (xr) => Record.Field(xr, xf) <> null), null)
                                    in if xrec = null then null
                                       else [fld = xf, src = xSrc, rec = xrec,
                                             flag = (List.Count(sr) = 1 and xrec[ts] = null)]))
                        in
                            [Entries = ents,
                             Amb = if List.IsEmpty(bad) then {}
                                   else {Lib[Amb](xVin, lastGrp, lastGrp{0}[source_timestamp_utc], bad)}],
            latestRes = List.Transform(srcs, LatestOne),
            entries = List.Combine(List.Transform(latestRes, (x) => x[Entries])),
            ambLatest = List.Combine(List.Transform(latestRes, (x) => x[Amb])),

            ConflictsFor = (xf as text) as list =>
                let
                    es = List.Sort(List.Select(entries, (e) => e[fld] = xf),
                                   (p, q) => Comparer.Ordinal(p[src], q[src])),
                    n = List.Count(es),
                    pairs = List.Combine(List.Transform({0..n - 2},
                                (i) => List.Transform({i + 1..n - 1}, (j) => {es{i}, es{j}})))
                in
                    List.Transform(
                        List.Select(pairs, (pr) => Record.Field(pr{0}[rec], xf) <> Record.Field(pr{1}[rec], xf)),
                        (pr) => ConflictRow(xVin, xf, pr{0}, pr{1})),
            conflicts = List.Combine(List.Transform(Attrs, ConflictsFor)),

            // ---- versions of one source record
            ids = List.Sort(List.Distinct(List.Transform(vr, (xr) => {xr[source_name], xr[source_record_id]})),
                            (p, q) => let c = Comparer.Ordinal(p{0}, q{0}) in if c <> 0 then c else Comparer.Ordinal(p{1}, q{1})),
            DriftOne = (xid as list) as record =>
                let
                    xSrc = xid{0},
                    xRid = xid{1},
                    versions = List.Select(vr, (xr) => xr[source_name] = xSrc and xr[source_record_id] = xRid),
                    groups = Lib[TsGroups](versions)
                in
                    if groups = null then
                        [Drifts = {}, Amb = {Lib[Amb](xVin, versions, "", Attrs)}]
                    else
                        let
                            PerField = (xf as text) as record =>
                                let
                                    badGrps = List.Select(groups, (g) =>
                                        List.Count(List.Distinct(List.RemoveNulls(List.Transform(g, (xr) => Record.Field(xr, xf))))) > 1),
                                    known = List.Transform(
                                        List.Select(groups, (g) => List.Count(List.RemoveNulls(List.Transform(g, (xr) => Record.Field(xr, xf)))) > 0),
                                        (g) => [rec = g{0}, val = List.First(List.RemoveNulls(List.Transform(g, (xr) => Record.Field(xr, xf))))]),
                                    k = List.Count(known),
                                    changed = List.Select({0..k - 2}, (i) => known{i}[val] <> known{i + 1}[val])
                                in
                                    if not List.IsEmpty(badGrps) then
                                        [Drifts = {},
                                         Amb = List.Transform(badGrps, (g) => Lib[Amb](xVin, g, g{0}[source_timestamp_utc], {xf}))]
                                    else
                                        [Drifts = List.Transform(changed, (i) => DriftRow(xVin, xf, xSrc, xRid, known{i}, known{i + 1})),
                                         Amb = {}],
                            perF = List.Transform(Attrs, PerField)
                        in
                            [Drifts = List.Combine(List.Transform(perF, (x) => x[Drifts])),
                             Amb = List.Combine(List.Transform(perF, (x) => x[Amb]))],
            driftRes = List.Transform(ids, DriftOne)
        in
            [Conflicts = conflicts,
             Drifts = List.Combine(List.Transform(driftRes, (x) => x[Drifts])),
             Amb = List.Combine({ambLatest, List.Combine(List.Transform(driftRes, (x) => x[Amb]))})],

    Results = List.Transform(Vins, PerVin),
    AllConflicts = List.Combine(List.Transform(Results, (x) => x[Conflicts])),
    AllDrifts = List.Combine(List.Transform(Results, (x) => x[Drifts])),
    AllAmb = List.Combine(List.Transform(Results, (x) => x[Amb])),
    Out = [Conflicts = Lib[ToTable](AllConflicts), Drifts = Lib[ToTable](AllDrifts), Candidates = Lib[CandTable](AllAmb)]
in
    Out
