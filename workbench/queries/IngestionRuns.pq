// Ingestion runs. Count columns are converted to whole numbers; a non-numeric value raises an error (never silently blanked).
// Reads ingestion_runs.csv from the DataFolder parameter. Every column is kept as TEXT exactly as extracted: no type
// guessing, no trimming, no replacement of empty or invalid values. Missing expected columns raise an error.
// QuoteStyle.Csv is required because quoted fields (payloads, error messages) may contain line breaks.
let
    Folder = Text.TrimEnd(DataFolder, {"\", "/"}),
    Source = Csv.Document(File.Contents(Folder & "\ingestion_runs.csv"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Expected = {"run_seq", "source_name", "status", "total_records", "inserted_records", "updated_records", "duplicate_records", "invalid_records", "failed_records", "error_message"},
    Selected = Table.SelectColumns(Promoted, Expected, MissingField.Error),
    AsText = Table.TransformColumnTypes(Selected, List.Transform(Expected, (c) => {c, type text})),
    Counts = Table.TransformColumnTypes(AsText, List.Transform({"run_seq", "total_records", "inserted_records", "updated_records", "duplicate_records", "invalid_records", "failed_records"}, (c) => {c, Int64.Type}), "en-US")
in
    Counts
