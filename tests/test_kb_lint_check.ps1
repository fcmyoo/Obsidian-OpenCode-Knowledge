# ============================================================
# KB Lint Check Tests (PowerShell)
# 适用于 Windows
# ============================================================
param(
    [string]$VaultTemplate = "$PSScriptRoot\..\vault-template"
)

$ErrorActionPreference = 'Stop'
$script = "$PSScriptRoot\..\scripts\kb-lint-check.ps1"

function New-TestVault {
    param([string]$Name)
    $path = Join-Path $env:TEMP ("kb-lint-test-{0}-{1}" -f $Name, [Guid]::NewGuid().ToString("N").Substring(0,8))
    $wiki = Join-Path $path "wiki"
    New-Item -ItemType Directory -Path $wiki -Force | Out-Null
    return $path
}

function Invoke-Lint {
    param([string]$VaultPath)
    $output = & $script -VaultPath $VaultPath -JsonMode 0 2>&1 | Out-String
    $lastExit = $LASTEXITCODE
    return [pscustomobject]@{
        Output = $output
        ExitCode = $lastExit
    }
}

function Assert-Contains {
    param($Result, [string]$Needle, [string]$Message)
    if ($Result.Output -notlike "*$Needle*") {
        throw "$Message :: missing '$Needle' in output`n$($Result.Output)"
    }
}

function Assert-NotContains {
    param($Result, [string]$Needle, [string]$Message)
    if ($Result.Output -like "*$Needle*") {
        throw "$Message :: unexpected '$Needle' in output`n$($Result.Output)"
    }
}

Write-Host "`n== KB Lint PowerShell Tests ==" -ForegroundColor Cyan

# Test 1: clean vault passes
$vault = New-TestVault -Name 'clean'
Set-Content -Path (Join-Path $vault 'wiki\index.md') -Value @'
---
title: Index
source: local
created: 2026-01-01
domain: wiki
---
- [Topic](../../wiki/Topic.md)
'@
Set-Content -Path (Join-Path $vault 'wiki\Topic.md') -Value @'
---
title: Topic
source: local
created: 2026-01-01
domain: wiki
---
# Topic
'@
Set-Content -Path (Join-Path $vault 'wiki\log.md') -Value '' -Encoding utf8
$r = Invoke-Lint -VaultPath $vault
if ($r.ExitCode -ne 0) { throw "clean vault should pass`n$($r.Output)" }
Assert-Contains -Result $r -Needle 'no broken wiki/relative links detected' -Message 'clean vault'
Assert-Contains -Result $r -Needle 'no missing raw sources detected' -Message 'clean vault'
Write-Host "[OK] clean vault passes" -ForegroundColor Green

# Test 2: missing vault fails
$r = Invoke-Lint -VaultPath 'Z:\does-not-exist'
if ($r.ExitCode -eq 0) { throw "missing vault should fail`n$($r.Output)" }
Assert-Contains -Result $r -Needle 'Vault not found' -Message 'missing vault'
Write-Host "[OK] missing vault fails" -ForegroundColor Green

# Test 3: broken link is reported
$vault = New-TestVault -Name 'broken'
Set-Content -Path (Join-Path $vault 'wiki\index.md') -Value @'
---
title: Index
source: local
created: 2026-01-01
domain: wiki
---
- [Topic](../../wiki/Topic.md)
'@
Set-Content -Path (Join-Path $vault 'wiki\Topic.md') -Value @'
---
title: Topic
source: local
created: 2026-01-01
domain: wiki
---
# Topic
[Bad](../../wiki/Missing.md)
'@
Set-Content -Path (Join-Path $vault 'wiki\log.md') -Value '' -Encoding utf8
$r = Invoke-Lint -VaultPath $vault
if ($r.ExitCode -eq 0) { throw "broken link should fail`n$($r.Output)" }
Assert-Contains -Result $r -Needle 'broken links detected' -Message 'broken link'
Write-Host "[OK] broken link is reported" -ForegroundColor Green

# Test 4: frontmatter missing fields is reported
$vault = New-TestVault -Name 'frontmatter'
Set-Content -Path (Join-Path $vault 'wiki\index.md') -Value @'
---
title: Index
source: local
created: 2026-01-01
domain: wiki
---
'@
Set-Content -Path (Join-Path $vault 'wiki\Topic.md') -Value '# Topic' -Encoding utf8
Set-Content -Path (Join-Path $vault 'wiki\log.md') -Value '' -Encoding utf8
$r = Invoke-Lint -VaultPath $vault
if ($r.ExitCode -eq 0) { throw "missing frontmatter should fail`n$($r.Output)" }
Assert-Contains -Result $r -Needle 'frontmatter missing fields detected' -Message 'frontmatter'
Write-Host "[OK] frontmatter missing fields is reported" -ForegroundColor Green

# Test 5: excessive tag duplicates is reported
$vault = New-TestVault -Name 'tags'
Set-Content -Path (Join-Path $vault 'wiki\index.md') -Value @'
---
title: Index
source: local
created: 2026-01-01
domain: wiki
tags: [ai]
---
'@
Set-Content -Path (Join-Path $vault 'wiki\Topic.md') -Value @'
---
title: Topic
source: local
created: 2026-01-01
domain: wiki
tags: [ai]
---
# Topic
'@
Set-Content -Path (Join-Path $vault 'wiki\Related.md') -Value @'
---
title: Related
source: local
created: 2026-01-01
domain: wiki
tags: [ai]
---
# Related
'@
Set-Content -Path (Join-Path $vault 'wiki\log.md') -Value '' -Encoding utf8
$r = Invoke-Lint -VaultPath $vault
if ($r.ExitCode -eq 0) { throw "tag duplicates should fail`n$($r.Output)" }
Assert-Contains -Result $r -Needle 'excessive tag duplicates detected' -Message 'tag duplicates'
Write-Host "[OK] excessive tag duplicates is reported" -ForegroundColor Green

Write-Host "`nAll PowerShell lint tests passed." -ForegroundColor Green
exit 0
