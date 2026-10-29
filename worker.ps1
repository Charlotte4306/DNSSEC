param([ValidateSet('compare','test')][string]$Action='compare')
$ErrorActionPreference='Stop'
Set-Location -LiteralPath $PSScriptRoot
function Compose {
    & docker compose @args
    if($LASTEXITCODE -ne 0){throw "Docker command failed: $LASTEXITCODE"}
}
function Measure-Worker([string]$run){
    $json=Compose exec -T client python /app/lab/api_worker.py compare --run-id $run
    return ($json -join "`n") | ConvertFrom-Json
}
function Access-Records([string]$run){
    $lines=Compose logs --no-color web-good web-fake
    foreach($line in $lines){
        if($line -match '\|\s*(\{.*\})$'){
            $entry=$Matches[1] | ConvertFrom-Json
            if($entry.run_id -eq $run){$entry}
        }
    }
}
if($Action -eq 'compare'){
    $run='worker-'+[guid]::NewGuid().ToString('N')
    Measure-Worker $run | ConvertTo-Json -Depth 20
    exit
}
try {
    & .\dns.ps1 baseline | Out-Null
    Compose exec -T client python -m unittest discover -s /app/tests -v
    foreach($phase in @('baseline','attack','recovery')){
        $modeAction=if($phase -eq 'recovery'){'recover'}else{$phase}
        & .\dns.ps1 $modeAction | Out-Null
        $run='worker-'+$phase+'-'+[guid]::NewGuid().ToString('N')
        $result=Measure-Worker $run
        if(-not $result.consistent){throw 'Scenario changed during measurement'}
        $plain=$result.results.plain; $secure=$result.results.secure
        $expectedPlain=if($phase -eq 'attack'){'training-fake'}else{'legitimate'}
        if($plain.http.status -ne 200 -or $plain.http.site_id -ne $expectedPlain -or $plain.http.error -or $plain.http.connected_ip -ne $plain.dns.answers[0]){throw 'Plain HTTP result failed'}
        if($phase -eq 'attack'){
            if($secure.dns.rcode -ne 'SERVFAIL' -or $secure.http.attempted -or $secure.http.request_sent -or $secure.http.body){throw 'Secure must stop at DNS'}
            $expectedCount=1
        }else{
            if($secure.http.status -ne 200 -or $secure.http.site_id -ne 'legitimate' -or -not $secure.dns.ad -or $secure.http.error -or $secure.http.connected_ip -ne $secure.dns.answers[0]){throw 'Secure HTTP result failed'}
            $expectedCount=2
        }
        $entries=@()
        for($i=0;$i -lt 10;$i++){
            $entries=@(Access-Records $run)
            if($entries.Count -ge $expectedCount){break}
            Start-Sleep -Milliseconds 200
        }
        if($entries.Count -ne $expectedCount){throw 'Unexpected number of HTTP access records'}
        foreach($entry in $entries){
            $branch=$entry.branch_id
            if($branch -notin @('plain','secure')){throw 'Unknown HTTP branch'}
            $measured=$result.results.$branch
            if($entry.site_id -ne $measured.http.site_id -or $entry.host -ne 'www.demo.test' -or $entry.path -ne '/' -or $entry.status -ne 200){throw 'HTTP log does not match worker result'}
        }
        if(@($entries | Where-Object branch_id -eq 'plain').Count -ne 1){throw 'Missing plain request'}
        if($phase -eq 'attack' -and @($entries | Where-Object branch_id -eq 'secure').Count -ne 0){throw 'Secure unexpectedly sent HTTP'}
        if($phase -ne 'attack' -and @($entries | Where-Object branch_id -eq 'secure').Count -ne 1){throw 'Missing secure request'}
        $directory=Join-Path 'evidence/runs' $run
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
        $result | ConvertTo-Json -Depth 20 | Set-Content (Join-Path $directory 'result.json') -Encoding utf8
        ConvertTo-Json -InputObject $entries -Depth 10 | Set-Content (Join-Path $directory 'http-access.json') -Encoding utf8
        Write-Host "PASS worker ${phase}: plain=$($plain.http.site_id); secure=$($secure.interpretation); HTTP access records=$($entries.Count)" -ForegroundColor Green
    }
} finally {
    & .\dns.ps1 recover | Out-Null
}
