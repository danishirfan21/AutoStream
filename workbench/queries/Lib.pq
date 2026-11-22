// Lib: shared constants and helper functions (a record). Mirrors reference_findings.py; see queries/README.md.
// Naming rule used throughout these scripts: inside an M record literal an identifier on the right-hand side that
// has the same name as a field of that literal refers to the FIELD (a cycle). Variables and parameters are
// therefore prefixed with "x"/"p" wherever a record literal is built, and every lambda is written explicitly.
[
    Columns = {"finding_id", "issue_type", "rule_id", "evidence_class", "assessment", "confirmed_invalid_input",
               "confirmed_pipeline_defect", "counts_as_actionable", "vin", "field", "source_a", "source_record_id_a",
               "timestamp_a", "value_a", "source_b", "source_record_id_b", "timestamp_b", "value_b",
               "pipeline_error_type_evidence", "distinct_record_count", "occurrences_canonical_sequence",
               "explained_by_finding_id", "derived_from", "fixture_evidence"},
    NoTs = "NO_SOURCE_TIMESTAMP",
    Attributes = {"year", "make", "model", "trim"},
    EmptyRow = Record.FromList(List.Repeat({""}, List.Count(Columns)), Columns),

    // A finding row: every column present, text, empty unless set. confirmed_pipeline_defect is always none_demonstrated.
    Blank = (pKv as record) as record =>
        Record.Combine({EmptyRow, [confirmed_pipeline_defect = "none_demonstrated"], pKv}),

    ToTable = (pRows as list) as table =>
        if List.IsEmpty(pRows) then #table(Columns, {}) else Table.FromRecords(pRows),

    CandTable = (pRows as list) as table =>
        if List.IsEmpty(pRows) then #table({"vin", "scope", "tskey", "fields", "rids"}, {}) else Table.FromRecords(pRows),

    SortOrd = (pList as list) as list => List.Sort(pList, Comparer.Ordinal),

    // Python str(): a missing key is "" (the .get default); a JSON null is "None".
    PyStr = (pRec as record, pField as text) as text =>
        if not Record.HasFields(pRec, pField) then ""
        else
            let xv = Record.Field(pRec, pField)
            in if xv = null then "None" else Text.From(xv, "en-US"),

    // Trimmed text, or null when absent/blank (same as Rec.get in the Python detector).
    Norm = (pValue as any) as nullable text =>
        if pValue = null then null
        else
            let xt = Text.Trim(Text.From(pValue, "en-US"))
            in if xt = "" then null else xt,

    // Logical field (year, make, model, trim, mileage, ...) of one payload, looked up through SourceMap.
    Field = (pPayload as record, pSource as text, pLogical as text) as nullable text =>
        let
            xName = Record.Field(Record.Field(SourceMap, pSource), pLogical),
            xValue = Record.FieldOrDefault(pPayload, xName, null)
        in
            Norm(xValue),

    // Digits and "-" only, then must look like -?digits. Anything else is null (not guessed).
    ParseMileage = (pText as nullable text) as nullable number =>
        if pText = null then null
        else
            let
                xd = Text.Select(pText, {"0".."9", "-"}),
                xbody = if Text.StartsWith(xd, "-") then Text.Range(xd, 1) else xd,
                xok = xbody <> "" and Text.Select(xbody, {"0".."9"}) = xbody
            in
                if xok then Number.FromText(xd, "en-US") else null,

    // Comparer: source name then record id, ordinal (Python sorts the tuple (source, rid)).
    CmpSR = (pA as record, pB as record) as number =>
        let xc = Comparer.Ordinal(pA[source_name], pB[source_name])
        in if xc <> 0 then xc else Comparer.Ordinal(pA[source_record_id], pB[source_record_id]),

    // Ascending groups of records that share a source timestamp (each group sorted by CmpSR).
    // null = ordering impossible (2+ records and at least one lacks a source timestamp).
    TsGroups = (pRecs as list) as nullable list =>
        if List.Count(pRecs) >= 2 and List.AnyTrue(List.Transform(pRecs, (xr) => xr[ts] = null)) then null
        else
            let xkeys = List.Sort(List.Distinct(List.Transform(pRecs, (xr) => xr[ts])))
            in List.Transform(xkeys, (xk) => List.Sort(List.Select(pRecs, (xr) => xr[ts] = xk), CmpSR)),

    ScopeOf = (pRecs as list) as text =>
        let xs = List.Distinct(List.Transform(pRecs, (xr) => xr[source_name]))
        in if List.Count(xs) = 1 then xs{0} else "*",

    // An ambiguity candidate. Candidates with the same (vin, scope, tskey) are merged later (query F_Ambiguous).
    Amb = (pVin as text, pRecs as list, pTs as text, pFields as list) as record =>
        [
            vin = pVin,
            scope = ScopeOf(pRecs),
            tskey = if pTs = "" then NoTs else pTs,
            fields = pFields,
            rids = List.Transform(pRecs, (xr) => xr[source_name] & ":" & xr[source_record_id])
        ],

    // Fields (of pFields) for which the non-null values within one group differ.
    DifferingFields = (pGroup as list, pFields as list) as list =>
        List.Select(pFields, (xf) =>
            List.Count(List.Distinct(List.RemoveNulls(List.Transform(pGroup, (xr) => Record.Field(xr, xf))))) > 1)
]
