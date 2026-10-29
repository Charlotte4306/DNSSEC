param([ValidateSet('baseline','attack','recover','compare','proof','logs','test')][string]$Action='compare')
$ErrorActionPreference='Stop'
Set-Location -LiteralPath $PSScriptRoot
function Compose {
    & docker compose @args
    if($LASTEXITCODE -ne 0){throw "Docker operation failed: $LASTEXITCODE"}
}
function Scenario { Compose exec -T client python /app/lab/dns_scenario.py @args }
function Mode([string]$value){
    Scenario $value
    foreach($server in @('plain','secure')){
        Compose exec -T $server unbound-control -c "/app/conf/$server.conf" flush_zone demo.test
    }
}
switch($Action){
    'baseline' { Mode off; Scenario baseline }
    'attack' { Mode on; Scenario attack }
    'recover' { Mode off; Scenario recovery }
    'compare' { Scenario compare }
    'proof' { Scenario proof }
    'logs' { Compose logs --tail 50 secure tamper }
    'test' {
        $since=(Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
        try {
            Mode off
            Compose exec -T client python -m unittest discover -s /app/tests -v
            Scenario baseline
            Mode on; Scenario attack
            Mode off; Scenario recovery
            $lines=Compose logs --since $since --no-color secure tamper
            $lines | Set-Content -LiteralPath 'evidence/dns-validation.log' -Encoding utf8
            if(-not ($lines -match 'signature crypto failed')){throw 'Expected crypto failure was not found in this test run logs'}
            Write-Host 'PASS dns-core: baseline, tamper, validation failure, recovery and log evidence.' -ForegroundColor Green
        } finally { Mode off }
    }
}
