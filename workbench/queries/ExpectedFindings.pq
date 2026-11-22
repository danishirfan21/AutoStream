// Approved golden findings (optional verification only). Read from the ExpectedFindingsPath parameter.
// Reads the file named by the ExpectedFindingsPath parameter. Every column is kept as TEXT exactly as extracted: no type
// guessing, no trimming, no replacement of empty or invalid values. Missing expected columns raise an error.
// QuoteStyle.Csv is required because quoted fields (payloads, error messages) may contain line breaks.
let
    Source = Csv.Document(File.Contents(ExpectedFindingsPath), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Expected = {"finding_id", "issue_type", "rule_id", "evidence_class", "assessment", "confirmed_invalid_input", "confirmed_pipeline_defect", "counts_as_actionable", "vin", "field", "source_a", "source_record_id_a", "timestamp_a", "value_a", "source_b", "source_record_id_b", "timestamp_b", "value_b", "pipeline_error_type_evidence", "distinct_record_count", "occurrences_canonical_sequence", "explained_by_finding_id", "derived_from", "fixture_evidence"},
    Selected = Table.SelectColumns(Promoted, Expected, MissingField.Error),
    AsText = Table.TransformColumnTypes(Selected, List.Transform(Expected, (c) => {c, type text}))
in
    AsText
