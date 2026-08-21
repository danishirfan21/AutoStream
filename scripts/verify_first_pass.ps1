$ErrorActionPreference = 'Stop'

if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose up -d --build

$deadline = (Get-Date).AddMinutes(2)
do {
  try { $health = Invoke-RestMethod http://localhost:8000/ready } catch { Start-Sleep -Seconds 2; continue }
} while ($health.status -ne 'ready' -and (Get-Date) -lt $deadline)
if ($health.status -ne 'ready') { throw 'API did not become ready' }

$first = Invoke-RestMethod -Method Post 'http://localhost:8000/api/v1/ingestion/csv?fixture=dealer_feed_v1.csv'
if ($first.inserted_records -ne 3 -or $first.invalid_records -ne 0) { throw 'Unexpected first import counts' }
$second = Invoke-RestMethod -Method Post 'http://localhost:8000/api/v1/ingestion/csv?fixture=dealer_feed_v1.csv'
if ($second.duplicate_records -ne 3 -or $second.inserted_records -ne 0) { throw 'Idempotency check failed' }

Invoke-RestMethod 'http://localhost:8000/api/v1/vehicles?make=Honda' | ConvertTo-Json -Depth 4
Push-Location backend
try { $env:PYTHONPATH='.'; python -m pytest tests -q } finally { Pop-Location }
Write-Host 'AUTOSTREAM FIRST-PASS VERIFY SUCCEEDED'
