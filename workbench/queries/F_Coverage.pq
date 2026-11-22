// F_Coverage: COVERAGE_GAP findings, one per (VIN, missing source). Same rules as reference_findings.py
// coverage_findings. A VIN present in one source's ACCEPTED records and absent from another source is a gap.
//   * COVERAGE_EXPLAINED   : the missing source has a rejected record for this VIN (links the REJECTED_RECORD finding).
//   * COVERAGE_FIXTURE_LIMITED : no explanation AND SyntheticFixtureMode = true (not actionable).
//   * COVERAGE_UNEXPLAINED : no explanation, real-data mode (default); actionable.
// The set of sources = sources seen in accepted records plus known sources seen in the rejection log.
let
    Recs = Table.ToRecords(SourceRecords),
    Known = Record.FieldNames(SourceMap),
    ErrSources = List.Select(List.Distinct(Raw_IngestionErrors[run_source_name]), (s) => s <> null and List.Contains(Known, s)),
    Sources = Lib[SortOrd](List.Distinct(List.Combine({List.Transform(Recs, (xr) => xr[source_name]), ErrSources}))),
    Rejected = Table.ToRecords(F_Rejected),
    Vins = Lib[SortOrd](List.Distinct(List.Transform(Recs, (xr) => xr[vin]))),

    RowsFor = (xVin as text) as list =>
        let
            vr = List.Select(Recs, (xr) => xr[vin] = xVin),
            present = Lib[SortOrd](List.Distinct(List.Transform(vr, (xr) => xr[source_name]))),
            missing = List.Select(Sources, (s) => not List.Contains(present, s))
        in
            List.Transform(missing, (xMissing) =>
                let
                    xSa = present{0},
                    xRa = List.First(List.Sort(List.Select(vr, (xr) => xr[source_name] = xSa),
                              (p, q) => let c = Comparer.Ordinal(q[source_timestamp_utc], p[source_timestamp_utc])
                                        in if c <> 0 then c else Comparer.Ordinal(q[source_record_id], p[source_record_id]))),
                    expl = Lib[SortOrd](List.Transform(
                              List.Select(Rejected, (r) => r[source_a] = xMissing and Text.Upper(Text.Trim(r[vin])) = xVin),
                              (r) => r[finding_id])),
                    xCls = if not List.IsEmpty(expl) then "COVERAGE_EXPLAINED"
                           else if SyntheticFixtureMode then "COVERAGE_FIXTURE_LIMITED"
                           else "COVERAGE_UNEXPLAINED",
                    xWhy = if xCls = "COVERAGE_EXPLAINED" then "A rejected record exists for this VIN in the missing source."
                           else if xCls = "COVERAGE_FIXTURE_LIMITED"
                           then "OBSERVATION CAUSED BY LIMITED SYNTHETIC FIXTURES; NOT A SOURCE DEFECT. Excluded from actionable defect counts."
                           else "No record and no rejected record in the missing source."
                in
                    Lib[Blank]([
                        finding_id = "COVERAGE_GAP|" & xVin & "|missing:" & xMissing,
                        issue_type = "COVERAGE_GAP",
                        rule_id = "SOURCE_COVERAGE",
                        evidence_class = xCls,
                        assessment = "COVERAGE_OBSERVATION",
                        confirmed_invalid_input = "not_applicable",
                        counts_as_actionable = if xCls = "COVERAGE_UNEXPLAINED" then "yes" else "no",
                        vin = xVin,
                        field = "source_presence",
                        source_a = xSa,
                        source_record_id_a = xRa[source_record_id],
                        timestamp_a = xRa[source_timestamp_utc],
                        value_a = "present",
                        source_b = xMissing,
                        value_b = "absent",
                        explained_by_finding_id = if List.IsEmpty(expl) then "" else expl{0},
                        derived_from = if List.IsEmpty(expl) then "FIXTURE_CONTENT" else "FIXTURE_CONTENT+PIPELINE_BEHAVIOR",
                        fixture_evidence = "VIN present in " & xSa & " accepted records, absent from " & xMissing & ". " & xWhy
                    ])),

    Result = Lib[ToTable](List.Combine(List.Transform(Vins, RowsFor)))
in
    Result
