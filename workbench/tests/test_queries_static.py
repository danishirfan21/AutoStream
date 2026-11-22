"""STATIC checks of workbench/queries/*.pq. These do NOT execute Power Query (no M engine is available here).
They catch structural mistakes and drift from the Python reference detector; they cannot prove the M logic works.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

import pytest

import reference_findings as rf

WB = Path(__file__).resolve().parents[1]
Q = WB / "queries"
EXPECTED_QUERIES = {
    "DataFolder", "SyntheticFixtureMode", "ExpectedFindingsPath", "SourceMap", "Lib", "Raw_SourceRecords",
    "Raw_IngestionErrors", "Vehicles", "PriceObservations", "IngestionRuns", "ExpectedFindings", "SourceRecords",
    "F_Mileage", "F_AttributeFindings", "F_Rejected", "F_Coverage", "F_Ambiguous", "Findings", "VinSourceLatest",
    "Checks",
}
PARAMETERS = {"DataFolder", "SyntheticFixtureMode", "ExpectedFindingsPath"}
KEYWORDS = {"let", "in", "if", "then", "else", "each", "and", "or", "not", "try", "otherwise", "error", "true",
            "false", "null", "as", "is", "type", "meta", "section", "shared"}


def read(name: str) -> str:
    return (Q / f"{name}.pq").read_text(encoding="utf-8")


def strip(src: str) -> str:
    """Remove comments; replace string literals by "" (keeps delimiters balanced and hides their content)."""
    out, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        if src.startswith("//", i):
            while i < n and src[i] != "\n":
                i += 1
        elif src.startswith("/*", i):
            j = src.find("*/", i + 2)
            assert j >= 0, "unterminated block comment"
            i = j + 2
        elif c == '"':
            i += 1
            while True:
                assert i < n, "unterminated string literal"
                if src[i] == '"':
                    if src.startswith('""', i):
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            out.append('""')
        else:
            out.append(c)
            i += 1
    return "".join(out)


def literals(src: str) -> list[str]:
    body = re.sub(r"//[^\n]*", "", src)
    return [m.replace('""', '"') for m in re.findall(r'"((?:[^"]|"")*)"', body)]


def all_names() -> set[str]:
    return {p.stem for p in Q.glob("*.pq")}


def test_exact_query_set():
    assert all_names() == EXPECTED_QUERIES


@pytest.mark.parametrize("name", sorted(EXPECTED_QUERIES))
def test_delimiters_balanced_and_shape(name):
    code = strip(read(name))
    stack = []
    pairs = {")": "(", "]": "[", "}": "{"}
    for ch in code:
        if ch in "([{":
            stack.append(ch)
        elif ch in ")]}":
            assert stack and stack.pop() == pairs[ch], f"{name}: mismatched {ch}"
    assert not stack, f"{name}: unclosed {stack}"
    if name not in PARAMETERS | {"SourceMap", "Lib"}:
        assert re.search(r"^let\b", code.strip(), re.M) and re.search(r"^in\b", code, re.M), f"{name}: needs let/in"
        assert len(re.findall(r"\blet\b", code)) == len(re.findall(r"\bin\b", code)), f"{name}: let/in count"
    assert "\t" not in read(name)


def test_parameters_are_marked_and_have_placeholder_paths_only_here():
    for p in PARAMETERS:
        assert "IsParameterQuery = true" in read(p)
    assert re.search(r"meta \[IsParameterQuery = true, Type = \"Logical\"", read("SyntheticFixtureMode"))
    assert read("SyntheticFixtureMode").splitlines()[-1].startswith("false meta"), "default must be real-data (false)"
    for name in EXPECTED_QUERIES - PARAMETERS:
        text = "\n".join(literals(read(name)))
        assert not re.search(r"[A-Za-z]:\\", text), f"{name}: hard-coded drive path"
        assert "CHANGE_ME" not in text


def test_files_are_read_only_through_parameters():
    for name in EXPECTED_QUERIES:
        code = strip(read(name))
        if "File.Contents" in code:
            assert name in {"Raw_SourceRecords", "Raw_IngestionErrors", "Vehicles", "PriceObservations",
                            "IngestionRuns", "ExpectedFindings"}, name
            assert "DataFolder" in code or "ExpectedFindingsPath" in code
    for banned in ("Sql.", "Odbc.", "PostgreSQL.", "Web.", "OleDb.", "Folder.Files", "Excel.CurrentWorkbook"):
        for name in EXPECTED_QUERIES:
            assert banned not in read(name), f"{name} uses {banned}"


def dependencies() -> dict[str, set[str]]:
    names = all_names()
    deps = {}
    for n in names:
        # identifiers that are not field accesses (x[Name]) and not definitions (Name = ...)
        idents = set(re.findall(r"(?<![\w.#\"\[])([A-Za-z_]\w*)(?!\w)(?!\s*=(?!=))(?!\])", strip(read(n))))
        deps[n] = (idents & names) - {n}
    return deps


def test_dependencies_form_a_dag_and_loaders_are_independent():
    deps = dependencies()
    state: dict[str, int] = {}

    def visit(n, path):
        assert state.get(n) != 1, f"cycle: {path + [n]}"
        if state.get(n) == 2:
            return
        state[n] = 1
        for d in deps[n]:
            visit(d, path + [n])
        state[n] = 2
    for n in deps:
        visit(n, [])
    for loader in ("Raw_SourceRecords", "Raw_IngestionErrors", "Vehicles", "PriceObservations", "IngestionRuns"):
        assert deps[loader] <= {"DataFolder"}, (loader, deps[loader])
    assert deps["SourceRecords"] >= {"Raw_SourceRecords", "Lib"}
    assert deps["Findings"] >= {"F_Mileage", "F_AttributeFindings", "F_Rejected", "F_Coverage", "F_Ambiguous", "Lib"}
    assert "Findings" not in deps["F_Mileage"] | deps["F_AttributeFindings"] | deps["F_Rejected"] | deps["F_Coverage"]
    assert "SyntheticFixtureMode" in deps["F_Rejected"] and "SyntheticFixtureMode" in deps["F_Coverage"]
    assert not any("SyntheticFixtureMode" in deps[n] for n in ("F_Mileage", "F_AttributeFindings", "F_Ambiguous"))


def test_source_map_mirrors_python_sources():
    text = strip(read("SourceMap"))
    raw = read("SourceMap")
    parsed = {}
    for src in re.findall(r"(\w+) = \[(.*?)\]", raw, re.S):
        parsed[src[0]] = dict(re.findall(r"(\w+) = \"([^\"]*)\"", src[1]))
    assert parsed == rf.SOURCES and text


def test_lib_columns_match_python_and_golden_header():
    cols = literals(read("Lib"))[: len(rf.COLUMNS)]
    assert cols == rf.COLUMNS
    with open(WB / "EXPECTED_FINDINGS.csv", newline="", encoding="utf-8") as fh:
        assert next(csv.reader(fh)) == rf.COLUMNS
    assert 'NoTs = "NO_SOURCE_TIMESTAMP"' in read("Lib") and rf.NO_TS == "NO_SOURCE_TIMESTAMP"
    assert 'Attributes = {"year", "make", "model", "trim"}' in read("Lib") and rf.ATTRIBUTES == ("year", "make", "model", "trim")


def test_semantic_constants_in_python_detector_all_appear_in_m():
    """Every rule id / class / assessment / ID prefix literal in the detector is present in some M query."""
    py = Path(rf.__file__).read_text(encoding="utf-8")
    py_lits = set(re.findall(r'"([A-Z][A-Z_+]{4,}(?:\|[a-z_:]*)?)"', py))
    m_lits = {lit for n in EXPECTED_QUERIES for lit in literals(read(n))}
    m_text = "\n".join(m_lits)
    ignore = {"ISO", "SOURCES", "COLUMNS", "ATTRIBUTES", "NO_TS", "VIN_RE", "FIXTURE_CONTENT+PIPELINE_BEHAVIOR"}
    missing = sorted(l for l in py_lits - ignore if l not in m_text)
    assert missing == [], missing
    assert "FIXTURE_CONTENT+PIPELINE_BEHAVIOR" in m_text


def test_finding_id_templates_match_the_specification():
    expect = {
        "F_Mileage": 'finding_id = "MILEAGE_REGRESSION|" & xVin & "|" & xCur[source_name] & "|" & xCur[source_record_id] & "|" & xCur[source_timestamp_utc]',
        "F_AttributeFindings": ['"ATTR_CONFLICT|" & xVin & "|" & xf & "|" & a[src] & "~" & b[src]',
                                '"ATTR_DRIFT|" & xVin & "|" & xf & "|" & xSrc & "|" & kb[rec][source_timestamp_utc]'],
        "F_Rejected": '"REJECTED_RECORD|" & xSrc & "|" & xKey & "|" & xRule & "|" & xTs',
        "F_Coverage": '"COVERAGE_GAP|" & xVin & "|missing:" & xMissing',
        "F_Ambiguous": '"AMBIGUOUS_ORDER|" & xk{0} & "|" & xk{1} & "|" & xk{2}',
    }
    for q, pats in expect.items():
        for pat in ([pats] if isinstance(pats, str) else pats):
            assert pat in read(q), (q, pat)
    # IDs never use database-generated values or exception names
    for q in ("F_Mileage", "F_AttributeFindings", "F_Rejected", "F_Coverage", "F_Ambiguous"):
        for m in re.finditer(r"finding_id = ([^\n]*)", read(q)):
            for banned in ("payload_hash", "run_seq", "error_type", "etype", "ingested", "uuid", "stored_source"):
                assert banned not in m.group(1), (q, banned)


def test_no_record_literal_field_is_used_bare_on_a_right_hand_side():
    """M pitfall: in [a = ... a ...] the right-hand `a` is the field itself (a cycle). Lint every record literal
    for a field whose right-hand side mentions its own name (x[a] / Rec.a style accesses are not flagged)."""
    problems = []
    for name in sorted(EXPECTED_QUERIES - {"Lib"}):  # Lib holds `let` bindings inside fields; its siblings are intentional
        code = strip(read(name))
        # collect literals: find "[" that starts a record literal ("[" followed by identifier and "=" , not preceded by an identifier/"]")
        for m in re.finditer(r"(?<![\w\]\)\}])\[\s*([A-Za-z_]\w*)\s*=(?!=)", code):
            start, depth, i = m.start(), 0, m.start()
            while True:
                ch = code[i]
                depth += ch in "[({"
                depth -= ch in "])}"
                i += 1
                if depth == 0:
                    break
            body = code[start + 1:i - 1]
            # split top-level fields
            fields, d, cur = [], 0, ""
            for ch in body:
                if ch in "[({":
                    d += 1
                elif ch in "])}":
                    d -= 1
                if ch == "," and d == 0:
                    fields.append(cur)
                    cur = ""
                else:
                    cur += ch
            fields.append(cur)
            names, rhs = [], {}
            for f in fields:
                mm = re.match(r"\s*([A-Za-z_]\w*)\s*=(?!=)(.*)$", f, re.S)
                if mm:
                    names.append(mm.group(1))
                    rhs[mm.group(1)] = mm.group(2)
            for fname, expr in rhs.items():  # only SELF references are certain bugs (siblings are used on purpose in Lib)
                if re.search(rf"(?<![\w.#\[\"]){re.escape(fname)}(?![\w\".])", expr):
                    problems.append((name, fname))
    assert problems == [], problems


def test_no_python_style_or_unqualified_functions_slipped_in():
    """Cheap guard against calling something that is not an M library function (typos like List.Contain)."""
    known = set("""List.Accumulate List.AllTrue List.AnyTrue List.Combine List.Contains List.Count List.Distinct List.First
    List.IsEmpty List.Last List.RemoveNulls List.Repeat List.Select List.Sort List.Sum List.Transform Record.Combine
    Record.Field Record.FieldNames Record.FieldOrDefault Record.FromList Record.HasFields Table.AddColumn Table.Column
    Table.Combine Table.FromRecords Table.FromRows Table.PromoteHeaders Table.RemoveColumns Table.RowCount
    Table.SelectColumns Table.Sort Table.ToRecords Table.TransformColumns Table.TransformColumnTypes Text.AfterDelimiter
    Text.Combine Text.From Text.Length Text.Lower Text.PositionOf Text.Range Text.Remove Text.Select Text.Split
    Text.Start Text.StartsWith Text.ToBinary Text.Trim Text.TrimEnd Text.Upper Lines.FromText Csv.Document
    File.Contents Json.Document DateTimeZone.FromText DateTimeZone.ToUtc Number.FromText Comparer.Ordinal
    Order.Ascending QuoteStyle.Csv MissingField.Error TextEncoding.Utf8 Int64.Type""".split())
    for name in EXPECTED_QUERIES:
        for fn in set(re.findall(r"\b((?:List|Record|Table|Text|Lines|Csv|File|Json|DateTimeZone|Number|Comparer|Order|"
                                 r"QuoteStyle|MissingField|TextEncoding|Int64)\.[A-Za-z0-9]+)", strip(read(name)))):
            assert fn in known, f"{name}: {fn}"
