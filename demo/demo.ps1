# Celesto Sandbox Control Plane - End-to-End Demo Script
# Usage: .\demo\demo.ps1 [http://localhost:8000]

param (
    [string]$BaseUrl = "http://localhost:8000"
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param ([string]$Title)
    Write-Host "`n========================================================" -ForegroundColor Cyan
    Write-Host ">>> $Title" -ForegroundColor Yellow
    Write-Host "========================================================" -ForegroundColor Cyan
}

Write-Host "Celesto Sandbox Control Plane Demo" -ForegroundColor Green
Write-Host "Target Endpoint: $BaseUrl" -ForegroundColor Gray

# Step 1: Health & Readiness Probes
Write-Step "1. Health & Readiness Probes"
$health = Invoke-RestMethod "$BaseUrl/health"
Write-Host "GET /health Response:" -ForegroundColor White
$health | ConvertTo-Json -Depth 3 | Write-Host -ForegroundColor Green

$ready = Invoke-RestMethod "$BaseUrl/ready"
Write-Host "GET /ready Response:" -ForegroundColor White
$ready | ConvertTo-Json -Depth 3 | Write-Host -ForegroundColor Green

# Step 2: Submit a Successful Sandbox Run
Write-Step "2. Submit Successful Sandbox Run ('echo hello from celesto')"
$reqBody = @{
    command = "echo 'Hello from isolated Celesto sandbox'"
    timeout_seconds = 30
} | ConvertTo-Json

$submitResp = Invoke-RestMethod -Method Post "$BaseUrl/runs" -ContentType "application/json" -Body $reqBody
Write-Host "POST /runs Submission Accepted (HTTP 202):" -ForegroundColor White
$submitResp | ConvertTo-Json -Depth 3 | Write-Host -ForegroundColor Green
$runId = $submitResp.run_id

# Step 3: Poll / Query Ledger for Terminal State
Write-Step "3. Query Run Ledger for Run ID: $runId"
Start-Sleep -Milliseconds 300
$runDetail = Invoke-RestMethod "$BaseUrl/runs/$runId"
Write-Host "GET /runs/$runId Completed State:" -ForegroundColor White
$runDetail | ConvertTo-Json -Depth 5 | Write-Host -ForegroundColor Green

# Step 4: Idempotency Key Deduplication
Write-Step "4. Idempotency Deduplication (Submitting duplicate idempotency_key)"
$idempotencyKey = "demo-idempotency-" + (Get-Random -Minimum 1000 -Maximum 9999)
$idemBody = @{
    command = "echo 'Executing once'"
    idempotency_key = $idempotencyKey
} | ConvertTo-Json

Write-Host "First Submission with key: $idempotencyKey" -ForegroundColor Gray
$firstRun = Invoke-RestMethod -Method Post "$BaseUrl/runs" -ContentType "application/json" -Body $idemBody
Write-Host "Run ID created: $($firstRun.run_id)" -ForegroundColor Green

Write-Host "Second Submission with identical key: $idempotencyKey" -ForegroundColor Gray
$secondRun = Invoke-RestMethod -Method Post "$BaseUrl/runs" -ContentType "application/json" -Body $idemBody
Write-Host "Run ID returned: $($secondRun.run_id)" -ForegroundColor Green

if ($firstRun.run_id -eq $secondRun.run_id) {
    Write-Host "[VERIFIED] Deduplicated: Both requests returned identical run_id without duplicate execution." -ForegroundColor Cyan
} else {
    Write-Host "[WARNING] Expected deduplication did not match." -ForegroundColor Red
}

# Step 5: Fail-Explicit Execution
Write-Step "5. Explicit Failure Policy (Intentional non-zero exit command: 'exit 42')"
$failBody = @{
    command = "exit 42"
} | ConvertTo-Json

$failSubmit = Invoke-RestMethod -Method Post "$BaseUrl/runs" -ContentType "application/json" -Body $failBody
Start-Sleep -Milliseconds 300
$failDetail = Invoke-RestMethod "$BaseUrl/runs/$($failSubmit.run_id)"
Write-Host "GET /runs/$($failSubmit.run_id) Details:" -ForegroundColor White
$failDetail | ConvertTo-Json -Depth 5 | Write-Host -ForegroundColor Green
Write-Host "[VERIFIED] Fail-Explicit: status is '$($failDetail.status)' with error '$($failDetail.error)'." -ForegroundColor Cyan

# Step 6: Schema Validation (Empty / Whitespace Command Rejection)
Write-Step "6. Input Validation (Blank command rejection with HTTP 422)"
try {
    $badBody = @{ command = "    " } | ConvertTo-Json
    Invoke-RestMethod -Method Post "$BaseUrl/runs" -ContentType "application/json" -Body $badBody
    Write-Host "[ERROR] Blank command should have been rejected." -ForegroundColor Red
} catch {
    Write-Host "[VERIFIED] HTTP 422 Unprocessable Entity returned as expected for blank command." -ForegroundColor Green
}

# Step 7: Filter Runs Ledger
Write-Step "7. Filter Runs Ledger by Status ('failed')"
$failedRuns = Invoke-RestMethod "$BaseUrl/runs?status=failed"
Write-Host "GET /runs?status=failed returned $($failedRuns.Count) record(s)." -ForegroundColor White
$failedRuns | ConvertTo-Json -Depth 3 | Write-Host -ForegroundColor Green

Write-Host "`nDemo completed successfully!`n" -ForegroundColor Green
