// F_Ambiguous: AMBIGUOUS_ORDER findings. Emitted when records cannot be ordered by SOURCE timestamp (equal
// timestamps that disagree, or 2+ records where one lacks a timestamp). No value is selected and the dependent
// comparison is skipped (see F_Mileage / F_AttributeFindings). Candidates with the same (vin, scope, timestamp) are
// merged: fields and record ids are the sorted union. Scope is the source name, or "*" when several sources tie.
// The approved fixtures contain no ties and no missing timestamps, so this query returns zero rows on the sample.
let
    Cand = Table.Combine({F_Mileage[Candidates], F_AttributeFindings[Candidates]}),
    Rows = Table.ToRecords(Cand),
    Keys = List.Distinct(List.Transform(Rows, (xr) => {xr[vin], xr[scope], xr[tskey]})),
    Out = List.Transform(Keys, (xk) =>
        let
            items = List.Select(Rows, (xr) => xr[vin] = xk{0} and xr[scope] = xk{1} and xr[tskey] = xk{2}),
            xFields = Lib[SortOrd](List.Distinct(List.Combine(List.Transform(items, (xr) => xr[fields])))),
            xRids = Lib[SortOrd](List.Distinct(List.Combine(List.Transform(items, (xr) => xr[rids])))),
            xFieldText = Text.Combine(xFields, ",")
        in
            Lib[Blank]([
                finding_id = "AMBIGUOUS_ORDER|" & xk{0} & "|" & xk{1} & "|" & xk{2},
                issue_type = "AMBIGUOUS_ORDER",
                rule_id = "TIMESTAMP_ORDER_UNAMBIGUOUS",
                evidence_class = "ORDERING_AMBIGUITY",
                assessment = "AMBIGUOUS_NOT_RESOLVED",
                confirmed_invalid_input = "undetermined",
                counts_as_actionable = "yes",
                vin = xk{0},
                field = xFieldText,
                source_a = xk{1},
                timestamp_a = if xk{2} = Lib[NoTs] then "" else xk{2},
                value_a = "records=" & Text.Combine(xRids, ";"),
                derived_from = "FIXTURE_CONTENT",
                fixture_evidence = "Records cannot be ordered by source timestamp for field(s) " & xFieldText
                    & "; no value was selected and dependent comparisons were skipped."
            ])),
    Result = Lib[ToTable](Out)
in
    Result
