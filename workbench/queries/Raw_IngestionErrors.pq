// Raw rejection occurrences (one row per occurrence, not per distinct record)
// Reads ingestion_errors.csv from the DataFolder parameter. Every column is kept as TEXT exactly as extracted: no type
// guessing, no trimming, no replacement of empty or invalid values. Missing expected columns raise an error.
// QuoteStyle.Csv is required because quoted fields (payloads, error messages) may contain line breaks.
let
    Folder = Text.TrimEnd(DataFolder, {"\", "/"}),
    Source = Csv.Document(File.Contents(Folder & "\ingestion_errors.csv"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Expected = {"run_seq", "run_source_name", "occurrence_in_run", "stored_source_record_id", "error_type", "error_message", "raw_payload_json"},
    Selected = Table.SelectColumns(Promoted, Expected, MissingField.Error),
    AsText = Table.TransformColumnTypes(Selected, List.Transform(Expected, (c) => {c, type text}))
in
    AsText
