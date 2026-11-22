# Builds AutoStream_DQ_Workbench.xlsx with desktop Excel (COM) from CSV snapshots written by snapshot_tables.py.
#   python tools\snapshot_tables.py --out <dir>
#   powershell -STA -ExecutionPolicy Bypass -File tools\build_workbook.ps1 -SnapshotDir <dir> [-Out file.xlsx] [-Compat]
# -Compat writes INDEX/MATCH instead of XLOOKUP so an Excel without XLOOKUP (e.g. 2016) can calculate and check the logic.
# The final workbook (no -Compat) contains XLOOKUP; it needs Excel 2021 / Microsoft 365 to calculate.
# The build runs in phases; each phase opens the file in a fresh Excel, saves, and is retried on COM errors
# (an unlicensed Excel intermittently rejects calls with RPC_E_CALL_REJECTED). Touches only the output file.
param(
    [Parameter(Mandatory = $true)][string]$SnapshotDir,
    [string]$Out,
    [switch]$Compat
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
if (-not $Out) { $Out = Join-Path $Root 'AutoStream_DQ_Workbench.xlsx' }
$SnapshotDir = (Resolve-Path $SnapshotDir).Path
$Missing = [Type]::Missing
$NumericCols = @('record_count', 'mileage', 'observed', 'run_seq', 'total_records', 'inserted_records', 'updated_records', 'duplicate_records', 'invalid_records', 'failed_records')
$SheetNames = 'README', 'Scorecard', 'Findings', 'Reconcile', 'Pivots', 'InvestigationLog', 'Checks', 'SourceRecords', 'Latest', 'Runs', 'Vehicles'

function Step($m) { Write-Host ("[build] " + $m) }

function Lk([string]$key, [string]$tbl, [string]$keyCol, [string]$retCol, [string]$default) {
    if ($Compat) { return "IFERROR(INDEX($tbl[$retCol],MATCH(SUBSTITUTE($key,""~"",""~~""),$tbl[$keyCol],0)),$default)" }
    return "_xlfn.XLOOKUP($key,$tbl[$keyCol],$tbl[$retCol],$default)"
}

function Write-Table($sheet, [string]$csv, [string]$name) {
    $rows = @(Import-Csv -Path (Join-Path $SnapshotDir $csv) -Encoding UTF8)
    $cols = @($rows[0].PSObject.Properties.Name)
    $n = $rows.Count + 1; $m = $cols.Count
    $arr = New-Object 'object[,]' $n, $m
    for ($c = 0; $c -lt $m; $c++) {
        $arr[0, $c] = $cols[$c]
        for ($r = 0; $r -lt $rows.Count; $r++) {
            $v = [string]$rows[$r].($cols[$c])
            if ($NumericCols -contains $cols[$c] -and $v -ne '') { $arr[($r + 1), $c] = [double]$v } else { $arr[($r + 1), $c] = $v }
        }
    }
    $rng = $sheet.Range('A1').Resize($n, $m)
    for ($c = 0; $c -lt $m; $c++) {
        if ($NumericCols -notcontains $cols[$c]) { $sheet.Range('A1').Offset(0, $c).Resize($n, 1).NumberFormat = '@' }
    }
    $rng.Value2 = $arr
    $lo = $sheet.ListObjects.Add(1, $rng, $Missing, 1)
    $lo.Name = $name; $lo.TableStyle = 'TableStyleMedium2'
}

# ------------------------------------------------------------------ phases (each gets $xl and $wb)
function Phase-Tables($xl, $wb) {
    while ($wb.Worksheets.Count -gt 1) { $wb.Worksheets.Item($wb.Worksheets.Count).Delete() }
    $wb.Worksheets.Item(1).Name = 'README'
    foreach ($n in $SheetNames[1..($SheetNames.Count - 1)]) {
        $s = $wb.Worksheets.Add($Missing, $wb.Worksheets.Item($wb.Worksheets.Count)); $s.Name = $n
    }
    Write-Table $wb.Worksheets.Item('Findings') 'findings.csv' 'tblFindings'
    Write-Table $wb.Worksheets.Item('Latest') 'latest.csv' 'tblLatest'
    Write-Table $wb.Worksheets.Item('Checks') 'checks.csv' 'tblChecks'
    Write-Table $wb.Worksheets.Item('SourceRecords') 'source_records.csv' 'tblSourceRecords'
    Write-Table $wb.Worksheets.Item('Runs') 'runs.csv' 'tblRuns'
    Write-Table $wb.Worksheets.Item('Vehicles') 'vehicles.csv' 'tblVehicles'
}

function Phase-Formatting($xl, $wb) {
    foreach ($n in 'Findings', 'Latest', 'Checks', 'SourceRecords', 'Runs', 'Vehicles') {
        $s = $wb.Worksheets.Item($n)
        $s.Rows.Item(1).Font.Bold = $true
        $s.Range('A:Z').ColumnWidth = 22      # AutoFit is unavailable in an unlicensed Excel
    }
    $wb.Worksheets.Item('Checks').Columns.Item(1).ColumnWidth = 90
    $fs = $wb.Worksheets.Item('Findings'); $fl = $fs.ListObjects.Item('tblFindings')
    $fs.Columns.Item(1).ColumnWidth = 62
    $body = $fl.DataBodyRange
    foreach ($r in @(@('=$D2="SOURCE_DISCREPANCY"', 13431551), @('=$D2="REJECTED_INPUT"', 13421823), @('=LEFT($D2,8)="COVERAGE"', 15921906), @('=$D2="ORDERING_AMBIGUITY"', 16247773))) {
        $fc = $body.FormatConditions.Add(2, $Missing, $r[0]); $fc.Interior.Color = $r[1]
    }
    $act = $fl.ListColumns.Item('counts_as_actionable').DataBodyRange
    $fc = $act.FormatConditions.Add(1, 3, '="yes"'); $fc.Font.Bold = $true; $fc.Font.Color = 192
    $cs = $wb.Worksheets.Item('Checks'); $stc = $cs.ListObjects.Item('tblChecks').ListColumns.Item('status').DataBodyRange
    $cf = $stc.FormatConditions.Add(1, 3, '="REVIEW"'); $cf.Interior.Color = 13431551; $cf.Font.Bold = $true
    $cf = $stc.FormatConditions.Add(1, 3, '="PASS"');   $cf.Interior.Color = 13561798
}

function Phase-Log($xl, $wb) {
    $ls = $wb.Worksheets.Item('InvestigationLog')
    $hdr = 'finding_id', 'status', 'owner', 'root_cause_hypothesis', 'evidence', 'resolution', 'opened_on', 'last_updated', 'issue_type_at_logging', 'evidence_snapshot', 'in_current_run', 'evidence_now', 'change_flag', 'duplicate_key'
    $seed = @(Import-Csv (Join-Path $SnapshotDir 'findings.csv') | Where-Object { $_.evidence_class -eq 'SOURCE_DISCREPANCY' })
    $arr = New-Object 'object[,]' ($seed.Count + 1), $hdr.Count
    for ($i = 0; $i -lt $hdr.Count; $i++) { $arr[0, $i] = $hdr[$i] }
    $today = (Get-Date).Date.ToOADate()
    for ($k = 0; $k -lt $seed.Count; $k++) {
        $f = $seed[$k]; $r = $k + 1
        $arr[$r, 0] = $f.finding_id; $arr[$r, 1] = 'Open'; $arr[$r, 3] = '(not yet investigated)'
        $arr[$r, 4] = $f.field + ': ' + $f.source_a + '=' + $f.value_a + ' @' + $f.timestamp_a + ' | ' + $f.source_b + '=' + $f.value_b + ' @' + $f.timestamp_b
        $arr[$r, 6] = $today; $arr[$r, 8] = $f.issue_type; $arr[$r, 9] = $f.value_a + ' | ' + $f.value_b
    }
    $ls.Range('A1:A500').NumberFormat = '@'
    $rng = $ls.Range('A1').Resize($seed.Count + 1, $hdr.Count)
    $rng.Value2 = $arr
    $ll = $ls.ListObjects.Add(1, $rng, $Missing, 1)
    $ll.Name = 'tblInvestigationLog'; $ll.TableStyle = 'TableStyleMedium9'
    $ll.ListColumns.Item('in_current_run').DataBodyRange.Formula = '=IF(SUMPRODUCT(--(tblFindings[finding_id]=[@[finding_id]]))>0,"yes","NO")'
    $evNow = '=IFERROR(' + (Lk '[@[finding_id]]' 'tblFindings' 'finding_id' 'value_a' '""') + '&" | "&' + (Lk '[@[finding_id]]' 'tblFindings' 'finding_id' 'value_b' '""') + ',"")'
    $ll.ListColumns.Item('evidence_now').DataBodyRange.Formula = $evNow
    $ll.ListColumns.Item('change_flag').DataBodyRange.Formula = '=IF([@[in_current_run]]="NO","DISAPPEARED",IF([@[evidence_snapshot]]="","OK",IF([@[evidence_snapshot]]=[@[evidence_now]],"OK","EVIDENCE CHANGED")))'
    $ll.ListColumns.Item('duplicate_key').DataBodyRange.Formula = '=IF(SUMPRODUCT(--([finding_id]=[@[finding_id]]))>1,"DUPLICATE","")'
}

function Phase-LogFormat($xl, $wb) {
    $ls = $wb.Worksheets.Item('InvestigationLog'); $ll = $ls.ListObjects.Item('tblInvestigationLog')
    $stat = $ll.ListColumns.Item('status').DataBodyRange
    $stat.Validation.Delete()
    $stat.Validation.Add(3, 1, 1, 'Open,In progress,Needs source info,Closed - no issue,Closed - data issue,Closed - system issue,Will not fix') | Out-Null
    $widths = 58, 18, 14, 30, 62, 30, 12, 12, 20, 24, 13, 24, 18, 14
    for ($c = 0; $c -lt 14; $c++) { $ls.Columns.Item($c + 1).ColumnWidth = $widths[$c] }
    $ll.ListColumns.Item('opened_on').DataBodyRange.NumberFormat = 'yyyy-mm-dd'
    $ll.ListColumns.Item('last_updated').DataBodyRange.NumberFormat = 'yyyy-mm-dd'
    $ls.Range('D2:F60').WrapText = $true
    $cf = $ls.Range('M2:M500').FormatConditions.Add(2, $Missing, '=M2="DISAPPEARED"');      $cf.Interior.Color = 12566463; $cf.Font.Bold = $true
    $cf = $ls.Range('M2:M500').FormatConditions.Add(2, $Missing, '=M2="EVIDENCE CHANGED"'); $cf.Interior.Color = 13431551
    $cf = $ls.Range('N2:N500').FormatConditions.Add(2, $Missing, '=N2="DUPLICATE"');        $cf.Interior.Color = 13421823
    $cf = $ls.Range('B2:B500').FormatConditions.Add(2, $Missing, '=LEFT(B2,6)="Closed"');   $cf.Font.Color = 8421504
    $ls.Range('P1').Value2 = 'Findings not yet logged'; $ls.Range('P1').Font.Bold = $true
    $ls.Range('P2').Formula = '=ROWS(tblFindings[finding_id])-COUNTIF(tblInvestigationLog[in_current_run],"yes")'
    $ls.Range('P3').Value2 = 'Not-yet-logged findings are shown in blue italic on the Findings sheet (finding_id column).'
    $ls.Range('P4').Value2 = 'Log a finding: copy its finding_id, Paste Special > Values into the next empty row (column A).'
    $ls.Range('P5').Value2 = 'The log is typed work and is never touched by a data refresh.'
    $ls.Columns.Item(16).ColumnWidth = 85
    [void]$wb.Names.Add('LoggedIds', '=InvestigationLog!$A$2:$A$500')
    $fs = $wb.Worksheets.Item('Findings'); $fl = $fs.ListObjects.Item('tblFindings')
    $cf = $fl.ListColumns.Item('finding_id').DataBodyRange.FormatConditions.Add(2, $Missing, '=SUMPRODUCT(--(LoggedIds=A2))=0'); $cf.Font.Italic = $true; $cf.Font.Color = 16711680
}

function Phase-Reconcile($xl, $wb) {
    $vins = @(Import-Csv (Join-Path $SnapshotDir 'latest.csv') | ForEach-Object { $_.vin } | Sort-Object -Unique)
    $rs = $wb.Worksheets.Item('Reconcile')
    $rs.Range('A1').Value2 = 'Cross-source reconciliation: latest accepted record per VIN and source (from tblLatest). Blank = latest value cannot be chosen (tie / missing timestamp); see status columns.'
    $rs.Range('A1').Font.Bold = $true
    $rs.Range('A2').Formula = '="VIN-source rows in tblLatest whose VIN is not listed below (add the VIN in column A, fill row formulas down): "&SUMPRODUCT(--(COUNTIF($A$5:$A$34,tblLatest[vin])=0))'
    $rs.Range('C3').Value2 = 'TRIM (latest)'; $rs.Range('F3').Value2 = 'MILEAGE (latest)'; $rs.Range('I3').Value2 = 'LATEST-RECORD STATUS'; $rs.Range('K3').Value2 = 'FINDINGS (tblFindings)'
    $h4 = 'vin', 'vehicle', 'dealer_csv', 'marketplace_json', 'trim check', 'dealer_csv', 'marketplace_json', 'mileage check', 'dealer_csv', 'marketplace_json', 'findings', 'actionable'
    for ($i = 0; $i -lt $h4.Count; $i++) { $rs.Cells.Item(4, $i + 1).Value2 = $h4[$i] }
    $rs.Range('A5:A34').NumberFormat = '@'
    for ($i = 0; $i -lt $vins.Count; $i++) { $rs.Cells.Item(5 + $i, 1).Value2 = $vins[$i] }
}

function Phase-ReconcileFormulas($xl, $wb) {
    $rs = $wb.Worksheets.Item('Reconcile')
    function KeyOf($col) { return '$A5&"|"&' + $col + '$4' }
    function TrimF($col) { $l = Lk (KeyOf $col) 'tblLatest' 'key' 'trim' '"NO RECORD"'; return '=IF($A5="","",IF(' + $l + '="","(blank)",' + $l + '))' }
    function MilF($col)  { $l = Lk (KeyOf $col) 'tblLatest' 'key' 'mileage' '"NO RECORD"'; return '=IF($A5="","",IF(' + $l + '="","(blank)",' + $l + '))' }
    function StatF($col) { return '=IF($A5="","",' + (Lk (KeyOf $col) 'tblLatest' 'key' 'status' '"NO RECORD"') + ')' }
    $veh = '=IF($A5="","",' + (Lk '$A5' 'tblVehicles' 'vin' 'year' '"?"') + '&" "&' + (Lk '$A5' 'tblVehicles' 'vin' 'make' '"?"') + '&" "&' + (Lk '$A5' 'tblVehicles' 'vin' 'model' '"?"') + ')'
    $rs.Range('B5:B34').Formula = $veh
    $rs.Range('C5:C34').Formula = (TrimF 'C'); $rs.Range('D5:D34').Formula = (TrimF 'D')
    $rs.Range('E5:E34').Formula = '=IF($A5="","",IF(OR(C5="NO RECORD",D5="NO RECORD"),"single source",IF(OR(C5="(blank)",D5="(blank)"),"unknown",IF(EXACT(C5,D5),"match","CONFLICT"))))'
    $rs.Range('F5:F34').Formula = (MilF 'F'); $rs.Range('G5:G34').Formula = (MilF 'G')
    $rs.Range('H5:H34').Formula = '=IF($A5="","",IF(AND(ISNUMBER(F5),ISNUMBER(G5)),IF(G5<F5,"marketplace LOWER",IF(G5>F5,"marketplace higher","equal")),"n/a"))'
    $rs.Range('I5:I34').Formula = (StatF 'I'); $rs.Range('J5:J34').Formula = (StatF 'J')
    $rs.Range('K5:K34').Formula = '=IF($A5="","",COUNTIF(tblFindings[vin],$A5))'
    $rs.Range('L5:L34').Formula = '=IF($A5="","",COUNTIFS(tblFindings[vin],$A5,tblFindings[counts_as_actionable],"yes"))'
}

function Phase-ReconcileFormat($xl, $wb) {
    $rs = $wb.Worksheets.Item('Reconcile')
    $rs.Range('A3:L4').Font.Bold = $true
    $rs.Range('A4:L4').Interior.Color = 6299648; $rs.Range('A4:L4').Font.Color = 16777215
    $rs.Columns.Item(1).ColumnWidth = 22; $rs.Columns.Item(2).ColumnWidth = 26
    $rs.Range('C:J').ColumnWidth = 18
    $rs.Columns.Item(11).ColumnWidth = 10; $rs.Columns.Item(12).ColumnWidth = 11
    $rs.Range('F5:G34').HorizontalAlignment = -4152
    $cf = $rs.Range('E5:E34').FormatConditions.Add(2, $Missing, '=E5="CONFLICT"');          $cf.Interior.Color = 13421823; $cf.Font.Bold = $true
    $cf = $rs.Range('H5:H34').FormatConditions.Add(2, $Missing, '=H5="marketplace LOWER"'); $cf.Interior.Color = 13421823; $cf.Font.Bold = $true
    $cf = $rs.Range('C5:G34').FormatConditions.Add(2, $Missing, '=C5="NO RECORD"');         $cf.Font.Italic = $true; $cf.Font.Color = 8421504
    $cf = $rs.Range('I5:J34').FormatConditions.Add(2, $Missing, '=AND(I5<>"OK",I5<>"NO RECORD",I5<>"")'); $cf.Interior.Color = 13431551
    $cf = $rs.Range('L5:L34').FormatConditions.Add(1, 5, '=0');                              $cf.Interior.Color = 13431551; $cf.Font.Bold = $true
}

function Phase-Scorecard($xl, $wb) {
    $sc = $wb.Worksheets.Item('Scorecard')
    $sc.Range('A1').Value2 = 'AutoStream data quality scorecard'; $sc.Range('A1').Font.Size = 16; $sc.Range('A1').Font.Bold = $true
    $sc.Range('A2').Value2 = 'Flags warranting investigation, not confirmed defects. Figures describe the loaded sample only.'; $sc.Range('A2').Font.Italic = $true
    $items = @(
        @('VOLUME', $null, $null),
        @('Accepted source records', '=ROWS(tblSourceRecords[vin])', ''),
        @('Distinct VINs', '=SUMPRODUCT(1/COUNTIF(tblSourceRecords[vin],tblSourceRecords[vin]))', ''),
        @('Ingestion runs in the log', '=ROWS(tblRuns[run_seq])', ''),
        @('FINDINGS', $null, $null),
        @('Total findings', '=ROWS(tblFindings[finding_id])', ''),
        @('Findings that warrant investigation (counts_as_actionable = yes)', '=COUNTIFS(tblFindings[counts_as_actionable],"yes")', 'depends on the classification mode of the data load'),
        @('Mileage regressions', '=COUNTIFS(tblFindings[issue_type],"MILEAGE_REGRESSION")', 'later record has lower mileage; anomaly flag'),
        @('Attribute conflicts (cross-source)', '=COUNTIFS(tblFindings[issue_type],"ATTR_CONFLICT")', ''),
        @('Attribute drift (same source over time)', '=COUNTIFS(tblFindings[issue_type],"ATTR_DRIFT")', 'anomaly flag, not proven corruption'),
        @('Rejected records (distinct payloads)', '=COUNTIFS(tblFindings[issue_type],"REJECTED_RECORD")', ''),
        @('Rejection occurrences in the error log', '=SUMPRODUCT(VALUE("0"&tblFindings[occurrences_canonical_sequence]))', 'kept separate from distinct records'),
        @('Coverage gaps', '=COUNTIFS(tblFindings[issue_type],"COVERAGE_GAP")', ''),
        @('Ordering ambiguities', '=COUNTIFS(tblFindings[issue_type],"AMBIGUOUS_ORDER")', ''),
        @('RECONCILIATION (from the Reconcile sheet)', $null, $null),
        @('VINs with records from both sources', '=COUNTIF(Reconcile!$E$5:$E$34,"match")+COUNTIF(Reconcile!$E$5:$E$34,"CONFLICT")+COUNTIF(Reconcile!$E$5:$E$34,"unknown")', ''),
        @('VINs with a trim conflict', '=COUNTIF(Reconcile!$E$5:$E$34,"CONFLICT")', ''),
        @('VINs where marketplace mileage is lower than dealer', '=COUNTIF(Reconcile!$H$5:$H$34,"marketplace LOWER")', ''),
        @('VINs present in a single source only', '=COUNTIF(Reconcile!$E$5:$E$34,"single source")', ''),
        @('QUALITY RATES', $null, $null),
        @('Share of VINs with no actionable finding', '=1-COUNTIF(Reconcile!$L$5:$L$34,">0")/B6', ''),
        @('Latest-record status OK (VIN-source pairs)', '=COUNTIFS(tblLatest[status],"OK")/ROWS(tblLatest[key])', 'blank latest values are never guessed'),
        @('Ingestion invalid-record rate', '=SUM(tblRuns[invalid_records])/SUM(tblRuns[total_records])', 'invalid / total records across runs'),
        @('Integrity checks needing review', '=COUNTIFS(tblChecks[status],"REVIEW")', 'see the Checks sheet')
    )
    $r = 4
    foreach ($it in $items) {
        $sc.Cells.Item($r, 1).Value2 = $it[0]
        if ($null -eq $it[1]) {
            $band = $sc.Range("A${r}:C${r}"); $band.Interior.Color = 6299648; $band.Font.Color = 16777215; $band.Font.Bold = $true
        } else {
            $sc.Cells.Item($r, 2).Formula = $it[1]; $sc.Cells.Item($r, 3).Value2 = $it[2]
        }
        $r++
    }
    $sc.Columns.Item(1).ColumnWidth = 62; $sc.Columns.Item(2).ColumnWidth = 14; $sc.Columns.Item(3).ColumnWidth = 55
    $sc.Range('B4:B40').HorizontalAlignment = -4152; $sc.Range('C4:C40').Font.Color = 8421504
    $sc.Range('B24').NumberFormat = '0%'; $sc.Range('B25').NumberFormat = '0%'; $sc.Range('B26').NumberFormat = '0.0%'
    $sc.Range('A30').Value2 = 'Data: snapshot of the reference detector (synthetic-fixture mode) on the committed sample; see README / LIVE_REFRESH.md to switch the tables to live Power Query.'
    $sc.Range('A30').Font.Italic = $true
}

function Phase-Pivot($xl, $wb, [int]$which) {
    $ps = $wb.Worksheets.Item('Pivots')
    if ($which -eq 1) {
        $ps.Range('A1').Value2 = 'PivotTables: findings summary and investigation status (Data > Refresh All after the data or the log changes)'; $ps.Range('A1').Font.Bold = $true
        $ps.Columns.Item(1).ColumnWidth = 38
        $ps.Range('A3').Value2 = '1. Findings by issue type and actionability'; $ps.Range('A3').Font.Bold = $true
        $pt = $wb.PivotCaches().Create(1, 'tblFindings').CreatePivotTable($ps.Range('A4'), 'ptFindingsByType')
        $pt.PivotFields('issue_type').Orientation = 1; $pt.PivotFields('counts_as_actionable').Orientation = 2
        [void]$pt.AddDataField($pt.PivotFields('finding_id'), 'Findings', -4112)
    } elseif ($which -eq 2) {
        $ps.Range('A14').Value2 = '2. Findings by evidence class'; $ps.Range('A14').Font.Bold = $true
        $pt = $wb.PivotCaches().Create(1, 'tblFindings').CreatePivotTable($ps.Range('A15'), 'ptFindingsByEvidence')
        $pt.PivotFields('evidence_class').Orientation = 1
        [void]$pt.AddDataField($pt.PivotFields('finding_id'), 'Findings', -4112)
    } else {
        $ps.Range('A25').Value2 = '3. Investigation status'; $ps.Range('A25').Font.Bold = $true
        $pt = $wb.PivotCaches().Create(1, 'tblInvestigationLog').CreatePivotTable($ps.Range('A26'), 'ptInvestigationStatus')
        $pt.PivotFields('status').Orientation = 1; $pt.PivotFields('issue_type_at_logging').Orientation = 2
        [void]$pt.AddDataField($pt.PivotFields('finding_id'), 'Logged findings', -4112)
    }
}

function Phase-Config($xl, $wb) {
    $s = $wb.Worksheets.Add($Missing, $wb.Worksheets.Item('README')); $s.Name = 'Config'
    $s.Range('A1').Value2 = 'Power Query settings (read by the live queries via the tblConfig table). Edit column B only.'; $s.Range('A1').Font.Bold = $true
    $s.Range('A3').Value2 = 'Setting'; $s.Range('B3').Value2 = 'Value'; $s.Range('C3').Value2 = 'Note'
    $s.Range('A4').Value2 = 'DataFolderDefault'
    $s.Range('B4').Formula = '=LEFT(CELL("filename",A1),FIND("[",CELL("filename",A1))-1)&"sample"'
    $s.Range('C4').Value2 = 'Formula: the "sample" folder next to this workbook (no machine-specific path). Leave as is.'
    $s.Range('A5').Value2 = 'DataFolderOverride'
    $s.Range('C5').Value2 = 'Optional. Type a full folder path to load other CSVs (e.g. a modified copy); clear the cell to return to the default folder.'
    $s.Range('A6').Value2 = 'SyntheticFixtureMode'
    $s.Range('B6').NumberFormat = '@'; $s.Range('B6').Value2 = 'true'
    $s.Range('C6').Value2 = 'true = demonstration data: 10 findings, 4 actionable. false = real-data classification: 9 actionable.'
    $lo = $s.ListObjects.Add(1, $s.Range('A3:C6'), $Missing, 1); $lo.Name = 'tblConfig'; $lo.TableStyle = 'TableStyleMedium2'
    $s.Range('A:A').ColumnWidth = 24; $s.Range('B:B').ColumnWidth = 70; $s.Range('C:C').ColumnWidth = 110
}

function Phase-Readme($xl, $wb) {
    $rd = $wb.Worksheets.Item('README')
    $lines = @(
        'AutoStream Data Quality Workbench',
        '',
        'Purpose: reconcile vehicle records from the dealer CSV and marketplace JSON sources, flag data-quality anomalies, and track investigations. Findings are flags that warrant investigation, not proven defects.',
        '',
        'DATA MODE: SNAPSHOT (until the live queries are connected). The data tables (Findings, Latest, Checks, SourceRecords, Runs, Vehicles) hold results of the Python reference detector in synthetic-fixture mode on the committed sample (10 findings, 4 actionable). They were NOT produced by Power Query. Reconciliation, scorecard, pivots and log are live formulas/pivots over those tables.',
        'GO LIVE (about 10 minutes, once): follow workbench\LIVE_REFRESH.md. Six bundled queries (workbench\queries\bundled) recompute the tables from the CSVs in the Config sheet DataFolder; after that, Data > Refresh All is the whole workflow.',
        '',
        'SHEETS',
        'Scorecard - counts and quality rates.   Findings - tblFindings with stable finding_id, evidence class, actionable flag (colour-coded; blue italic id = not yet in the log).',
        'Reconcile - one row per VIN: latest dealer vs marketplace trim and mileage via XLOOKUP, conflicts highlighted. New VINs: type the VIN in column A and fill the row down.',
        'Pivots - PivotTables: findings by type x actionable, by evidence class, investigation status.',
        'InvestigationLog - tblInvestigationLog: typed by the analyst, never overwritten by a data refresh. Keyed by finding_id.',
        '    change_flag: OK / DISAPPEARED (finding no longer produced) / EVIDENCE CHANGED. P2 counts findings not yet logged.',
        'Checks - integrity checks (PASS / REVIEW).   SourceRecords, Latest, Runs, Vehicles - supporting tables.',
        '',
        'LOG A FINDING: copy its finding_id on Findings, Paste Special > Values into the next empty row of InvestigationLog, then set status, owner, root-cause hypothesis, evidence, resolution.',
        'Do not type inside data tables (Findings, Checks, SourceRecords, Latest, Runs, Vehicles): a refresh or reload replaces them. Notes belong in InvestigationLog.',
        'After changing data or the log press Data > Refresh All (pivots also refresh on file open).',
        'Requires Excel 2021 or Microsoft 365 for XLOOKUP. If cells show #NAME?, press Ctrl+Alt+F9; older Excel cannot calculate XLOOKUP.',
        'Built ' + (Get-Date -Format 'yyyy-MM-dd') + ' by workbench\tools\build_workbook.ps1.'
    )
    for ($i = 0; $i -lt $lines.Count; $i++) { if ($lines[$i] -ne '') { $rd.Cells.Item($i + 1, 1).Value2 = $lines[$i] } }
    $rd.Range('A1').Font.Size = 18; $rd.Range('A1').Font.Bold = $true
    $rd.Range('A5').Font.Bold = $true; $rd.Range('A9').Font.Bold = $true
    $rd.Columns.Item(1).ColumnWidth = 200   # no WrapText: row auto-height fails ("Insufficient memory") in the unlicensed Excel
}

function Phase-PivotRefreshOnOpen($xl, $wb) {
    $ps = $wb.Worksheets.Item('Pivots')
    foreach ($nm in 'ptFindingsByType', 'ptFindingsByEvidence', 'ptInvestigationStatus') { $ps.PivotTables($nm).PivotCache().RefreshOnFileOpen = $true }
}

function Phase-Report($xl, $wb) {
    $xl.CalculateFull()
    $rs = $wb.Worksheets.Item('Reconcile'); $sc = $wb.Worksheets.Item('Scorecard'); $ls = $wb.Worksheets.Item('InvestigationLog'); $ps = $wb.Worksheets.Item('Pivots')
    Write-Host '--- Reconcile rows 5-9'
    for ($r2 = 5; $r2 -le 9; $r2++) { Write-Host ((1..12 | ForEach-Object { $rs.Cells.Item($r2, $_).Text }) -join ' | ') }
    Write-Host '--- Scorecard'
    for ($r2 = 5; $r2 -le 28; $r2++) { if ($sc.Cells.Item($r2, 2).Text -ne '') { Write-Host ('{0,-66} {1}' -f $sc.Cells.Item($r2, 1).Value2, $sc.Cells.Item($r2, 2).Text) } }
    Write-Host ('log flags: ' + ((2..6 | ForEach-Object { $ls.Cells.Item($_, 11).Text + '/' + $ls.Cells.Item($_, 13).Text + '/' + $ls.Cells.Item($_, 14).Text }) -join '  '))
    Write-Host ('log not-yet-logged: ' + $ls.Range('P2').Text + ' ; log rows: ' + $ls.ListObjects.Item('tblInvestigationLog').DataBodyRange.Rows.Count)
    foreach ($r2 in (4..13) + (15..22) + (26..33)) { Write-Host ('pivots r' + $r2 + ': ' + ((1..4 | ForEach-Object { $ps.Cells.Item($r2, $_).Text }) -join ' , ')) }
}

# ------------------------------------------------------------------ driver
function Invoke-Phase([string]$name, [scriptblock]$body, [bool]$create = $false, [bool]$save = $true) {
    for ($attempt = 1; $attempt -le 12; $attempt++) {
        $before = @(Get-Process excel -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
        $xl = $null; $wb = $null; $mine = @()
        $ok = $false
        try {
            $xl = New-Object -ComObject Excel.Application
            $mine = @(Get-Process excel -ErrorAction SilentlyContinue | Where-Object { $before -notcontains $_.Id } | ForEach-Object { $_.Id })
            $xl.Visible = $false; $xl.DisplayAlerts = $false
            if ($create) { $wb = $xl.Workbooks.Add() } else { $wb = $xl.Workbooks.Open($Out) }
            if ($null -eq $wb -or $wb.Worksheets.Count -lt 1) { throw 'workbook not ready' }
            & $body $xl $wb
            if ($save) {
                if ($create) { if (Test-Path $Out) { Remove-Item $Out -Force }; $wb.SaveAs($Out, 51) } else { $wb.Save() }
            }
            $ok = $true
        } catch {
            Write-Host ("[build] phase '$name' attempt $attempt failed: " + $_.Exception.Message.Split("`n")[0])
        } finally {
            try { if ($wb) { $wb.Close($false) } } catch { }
            try { if ($xl) { $xl.Quit() } } catch { }
            Start-Sleep -Seconds 2
            foreach ($p in $mine) { Get-Process -Id $p -ErrorAction SilentlyContinue | Stop-Process -Force }
            $mine = @()
        }
        if ($ok) { Step "phase '$name' ok (attempt $attempt)"; return }
        Start-Sleep -Seconds 2
    }
    throw "phase '$name' failed after 12 attempts"
}

$failed = $false
try {
    Invoke-Phase 'tables' { param($xl, $wb) Phase-Tables $xl $wb } $true
    Invoke-Phase 'table formatting' { param($xl, $wb) Phase-Formatting $xl $wb }
    Invoke-Phase 'investigation log' { param($xl, $wb) Phase-Log $xl $wb }
    Invoke-Phase 'log formatting' { param($xl, $wb) Phase-LogFormat $xl $wb }
    Invoke-Phase 'reconcile vins' { param($xl, $wb) Phase-Reconcile $xl $wb }
    Invoke-Phase 'reconcile formulas' { param($xl, $wb) Phase-ReconcileFormulas $xl $wb }
    Invoke-Phase 'reconcile formatting' { param($xl, $wb) Phase-ReconcileFormat $xl $wb }
    Invoke-Phase 'scorecard' { param($xl, $wb) Phase-Scorecard $xl $wb }
    Invoke-Phase 'pivot 1' { param($xl, $wb) Phase-Pivot $xl $wb 1 }
    Invoke-Phase 'pivot 2' { param($xl, $wb) Phase-Pivot $xl $wb 2 }
    Invoke-Phase 'pivot 3' { param($xl, $wb) Phase-Pivot $xl $wb 3 }
    Invoke-Phase 'config' { param($xl, $wb) Phase-Config $xl $wb }
    Invoke-Phase 'readme' { param($xl, $wb) Phase-Readme $xl $wb }
    if (-not $Compat) { Invoke-Phase 'pivot refresh on open' { param($xl, $wb) Phase-PivotRefreshOnOpen $xl $wb } }
    Step "saved $Out"
    if ($Compat) { Invoke-Phase 'compat report' { param($xl, $wb) Phase-Report $xl $wb } $false $false }
} catch { Write-Host ("[build] FAILED: " + $_.Exception.Message); $failed = $true }
if ($failed) { exit 1 }
