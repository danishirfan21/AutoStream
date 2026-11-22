// F_Rejected: REJECTED_RECORD findings, one per DISTINCT rejected input (Finding ID), with the number of
// rejection occurrences kept as evidence. Same rules as reference_findings.py rejected_findings:
//  * The record key comes from the stored PAYLOAD (dealer vin / marketplace listing_id), not from the positional
//    stored_source_record_id (row-N). The payload's own timestamp is part of the ID ("NO_SOURCE_TIMESTAMP" if absent).
//  * rule_id is derived from the stored error (type + message shape): InvalidOperation -> PRICE_NUMERIC; a
//    one-error ValidationError on field vin -> VIN_FORMAT; anything else -> UNCLASSIFIED (never guessed).
//    The exception type is evidence only (pipeline_error_type_evidence); the message text is NOT part of any ID.
//  * confirmed_invalid_input = yes only when the payload independently violates the stated rule.
//  * counts_as_actionable follows the SyntheticFixtureMode parameter (default false = real-data = yes).
let
    Errors = Table.ToRecords(Raw_IngestionErrors),
    Known = Record.FieldNames(SourceMap),

    CfgField = (xSrc as nullable text, xName as text) as text =>
        if xSrc <> null and List.Contains(Known, xSrc) then Record.Field(Record.Field(SourceMap, xSrc), xName) else "",

    ClassifyRule = (xType as nullable text, xMsg as nullable text) as text =>
        if xType = "InvalidOperation" then "PRICE_NUMERIC"
        else if xType = "ValidationError" and xMsg <> null then
            let
                lines = Lines.FromText(xMsg),
                firstLine = if List.IsEmpty(lines) then "" else lines{0},
                pos = Text.PositionOf(firstLine, " validation error"),
                countText = if pos < 0 then "" else Text.Start(firstLine, pos),
                rest = if pos < 0 then "" else Text.Range(firstLine, pos + Text.Length(" validation error")),
                headerOk = countText <> "" and Text.Select(countText, {"0".."9"}) = countText
                           and (Text.StartsWith(rest, " for ") or Text.StartsWith(rest, "s for ")),
                IsIdent = (l as text) as logical =>
                    l <> "" and Text.Select(Text.Start(l, 1), {"A".."Z", "a".."z", "_"}) <> ""
                    and Text.Select(l, {"A".."Z", "a".."z", "0".."9", "_", "."}) = l,
                fields = List.Select(lines, IsIdent)
            in
                if headerOk and countText = "1" and fields = {"vin"} then "VIN_FORMAT" else "UNCLASSIFIED"
        else "UNCLASSIFIED",

    // true/false = the payload does / does not violate the rule; null = cannot say.
    Violates = (xRule as text, xSrc as text, xp as record) as nullable logical =>
        if not List.Contains(Known, xSrc) then null
        else if xRule = "VIN_FORMAT" then
            let xv = Text.Upper(Text.Trim(Lib[PyStr](xp, CfgField(xSrc, "vin"))))
            in not (Text.Length(xv) = 17 and Text.Select(xv, {"A".."H", "J".."N", "P", "R".."Z", "0".."9"}) = xv)
        else if xRule = "PRICE_NUMERIC" then
            let
                xt = Text.Remove(Lib[PyStr](xp, CfgField(xSrc, "price")), {" ", "$", ",", "#(tab)", "#(lf)", "#(cr)"}),
                parts = Text.Split(xt, "."),
                ok = (List.Count(parts) = 1 or List.Count(parts) = 2)
                     and List.AllTrue(List.Transform(parts, (x) => x <> "" and Text.Select(x, {"0".."9"}) = x))
            in not ok
        else null,

    Parsed = List.Transform(Errors, (xe) =>
        let
            xSrc = xe[run_source_name],
            xp = Json.Document(Text.ToBinary(xe[raw_payload_json], TextEncoding.Utf8)),
            xRule = ClassifyRule(xe[error_type], xe[error_message]),
            xKeyRaw = Text.Trim(Lib[PyStr](xp, CfgField(xSrc, "record_key"))),
            xKey = if xKeyRaw <> "" then xKeyRaw else xe[stored_source_record_id],
            xTsVal = Record.FieldOrDefault(xp, CfgField(xSrc, "timestamp"), null),
            xTsText = if xTsVal = null or xTsVal = "" then "" else Text.From(xTsVal, "en-US"),
            xTs = if xTsText = "" then Lib[NoTs] else xTsText
        in
            [fid = "REJECTED_RECORD|" & xSrc & "|" & xKey & "|" & xRule & "|" & xTs,
             src = xSrc, rule = xRule, ts = xTs, stored = xe[stored_source_record_id], p = xp,
             ptext = xe[raw_payload_json], etype = xe[error_type]]),

    Fids = List.Distinct(List.Transform(Parsed, (xr) => xr[fid])),

    Rows = List.Transform(Fids, (xFid) =>
        let
            g = List.Select(Parsed, (xr) => xr[fid] = xFid),
            g0 = g{0},
            xSrc = g0[src],
            xRule = g0[rule],
            xp = g0[p],
            xFld = if xRule = "VIN_FORMAT" then CfgField(xSrc, "vin")
                   else if xRule = "PRICE_NUMERIC" then CfgField(xSrc, "price") else "",
            xDistinct = List.Count(List.Distinct(List.Transform(g, (xr) => xr[ptext]))),
            xOcc = List.Count(g)
        in
            Lib[Blank]([
                finding_id = xFid,
                issue_type = "REJECTED_RECORD",
                rule_id = xRule,
                evidence_class = "REJECTED_INPUT",
                assessment = "EXPECTED_REJECTION",
                confirmed_invalid_input = if Violates(xRule, xSrc, xp) = true then "yes" else "undetermined",
                counts_as_actionable = if SyntheticFixtureMode then "no" else "yes",
                vin = Lib[PyStr](xp, CfgField(xSrc, "vin")),
                field = xFld,
                source_a = xSrc,
                source_record_id_a = g0[stored],
                timestamp_a = if g0[ts] = Lib[NoTs] then "" else g0[ts],
                value_a = if xFld <> "" then xFld & "=" & Lib[PyStr](xp, xFld) else "",
                pipeline_error_type_evidence = Text.Combine(Lib[SortOrd](List.Distinct(List.Transform(g, (xr) => xr[etype]))), ";"),
                distinct_record_count = Text.From(xDistinct, "en-US"),
                occurrences_canonical_sequence = Text.From(xOcc, "en-US"),
                derived_from = "FIXTURE_CONTENT+PIPELINE_BEHAVIOR",
                fixture_evidence = Text.From(xOcc, "en-US") & " rejection occurrence(s) of " & Text.From(xDistinct, "en-US")
                    & " distinct payload(s) for rule " & xRule & "; stored record id " & g0[stored] & "."
            ])),

    Result = Lib[ToTable](Rows)
in
    Result
