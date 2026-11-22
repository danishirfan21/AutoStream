// Findings: the combined, de-duplicated findings (24 columns, all text, same columns as EXPECTED_FINDINGS.csv).
// Load as an Excel Table named tblFindings. finding_id is the stable key used by the investigation log.
// Every finding is an anomaly flag that warrants investigation; none is proof of a defect
// (confirmed_pipeline_defect is none_demonstrated on every row; counts_as_actionable is not "confirmed defect").
let
    Parts = {
        F_Mileage[Findings],
        F_AttributeFindings[Conflicts],
        F_AttributeFindings[Drifts],
        F_Rejected,
        F_Coverage,
        F_Ambiguous
    },
    All = Table.Combine(Parts),
    Ids = Table.Column(All, "finding_id"),
    Checked = if List.Count(Ids) <> List.Count(List.Distinct(Ids))
              then error "Duplicate finding_id values: finding ids must be unique"
              else All,
    Ordered = Table.SelectColumns(Checked, Lib[Columns]),
    Sorted = Table.Sort(Ordered, {{"issue_type", Order.Ascending}, {"finding_id", Order.Ascending}}),
    AsText = Table.TransformColumnTypes(Sorted, List.Transform(Lib[Columns], (c) => {c, type text}))
in
    AsText
