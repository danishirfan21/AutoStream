# Copies one Power Query script to the clipboard so it can be pasted into the Advanced Editor.
#   .\copy_query.ps1 -List                 shows the creation order
#   .\copy_query.ps1 Lib                   copies queries\Lib.pq
#   .\copy_query.ps1 -Next                 copies the next query in order (progress is kept in a temp file)
#   .\copy_query.ps1 -Reset                restarts -Next from the beginning
# DataFolder.pq / ExpectedFindingsPath.pq contain a placeholder path: after pasting, edit the value to your own path.
param([string]$Name, [switch]$List, [switch]$Next, [switch]$Reset)
$ErrorActionPreference = 'Stop'
$q = Join-Path (Split-Path -Parent $PSScriptRoot) 'queries'
$order = 'DataFolder','SyntheticFixtureMode','SourceMap','Lib','Raw_SourceRecords','Raw_IngestionErrors','SourceRecords',
         'F_Mileage','F_AttributeFindings','F_Rejected','F_Coverage','F_Ambiguous','Findings',
         'ExpectedFindingsPath','ExpectedFindings','VinSourceLatest','Checks','IngestionRuns','Vehicles','PriceObservations'
$state = Join-Path $env:TEMP 'dq_copy_query_state.txt'
if ($List)  { $i = 1; $order | ForEach-Object { '{0,2}. {1}' -f $i++, $_ }; return }
if ($Reset) { Remove-Item $state -ErrorAction SilentlyContinue; 'reset'; return }
if ($Next)  {
    $n = if (Test-Path $state) { [int](Get-Content $state) } else { 0 }
    if ($n -ge $order.Count) { 'All queries copied. Use -Reset to start over.'; return }
    $Name = $order[$n]; ($n + 1) | Set-Content $state
}
if (-not $Name) { throw 'Give a query name, or use -List / -Next.' }
$f = Join-Path $q "$Name.pq"; if (-not (Test-Path $f)) { $f = Join-Path $q (Join-Path 'bundled' "$Name.pq") }
if (-not (Test-Path $f)) { throw "No such query file: $f" }
Get-Content -Raw -Encoding UTF8 $f | Set-Clipboard
"Copied $Name to the clipboard. In Excel: Advanced Editor -> select all -> paste -> Done -> rename the query to: $Name"
