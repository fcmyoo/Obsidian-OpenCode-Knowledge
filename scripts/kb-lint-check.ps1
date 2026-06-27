# ============================================================
# Knowledge Base Lint Check
# 适用于 Windows
# ============================================================
param(
    [string]$VaultPath,
    [string]$JsonMode = "0"
)

if (-not $VaultPath) {
    $VaultPath = Join-Path (Get-Location) 'vault-template'
}

$ErrorActionPreference = "Continue"

function Write-OK { param($msg) Write-Output "[OK] $msg" }
function Write-WARN { param($msg) Write-Output "[WARN] $msg" }
function Write-ERR { param($msg) Write-Output "[ERR] $msg" }
function Write-Section { param($msg) Write-Host ""; Write-Host "== $msg ==" -ForegroundColor Cyan }

$wikiDir = Join-Path $VaultPath "wiki"
$indexFile = Join-Path $wikiDir "index.md"
$exitCode = 0
$issues = @()

Write-Section "Vault Checks"
if (-not (Test-Path $VaultPath)) {
    Write-ERR "Vault not found: $VaultPath"
    $issues += @{ check = "vault"; status = "error"; path = $VaultPath }
    $exitCode = 1
} else {
    Write-OK "Vault: $VaultPath"
    $issues += @{ check = "vault"; status = "ok"; path = $VaultPath }
}

if (-not (Test-Path $wikiDir)) {
    Write-ERR "wiki directory missing: $wikiDir"
    $issues += @{ check = "wiki_directory"; status = "error"; path = $wikiDir }
    $exitCode = 1
} else {
    Write-OK "wiki directory exists"
    $issues += @{ check = "wiki_directory"; status = "ok"; path = $wikiDir }
}

if (-not (Test-Path $indexFile)) {
    Write-ERR "missing index.md: $indexFile"
    $issues += @{ check = "index_file"; status = "error"; path = $indexFile }
    $exitCode = 1
} else {
    Write-OK "index.md exists"
    $issues += @{ check = "index_file"; status = "ok"; path = $indexFile }
}

$wikiFiles = Get-ChildItem -Path $wikiDir -Filter *.md -Recurse -File | Sort-Object FullName
Write-OK "wiki files found: $($wikiFiles.Count)"

$missingLinks = 0
foreach ($file in $wikiFiles) {
    $content = Get-Content -Path $file.FullName -Raw
    $matches = [regex]::Matches($content, '\[[^\[\]]+\]\(([^)]+)\)')
    foreach ($match in $matches) {
        $link = $match.Groups[1].Value
        if ([string]::IsNullOrWhiteSpace($link)) { continue }
        $resolved = $null
        if ($link -like 'wiki/*') {
            $resolved = Join-Path $VaultPath $link
        } elseif ($link -like '../*') {
            $relative = $link -replace '^\.\./', ''
            $resolved = Join-Path (Split-Path -Parent $file.Directory.FullName) $relative
        } else {
            $resolved = Join-Path $file.Directory.FullName $link
        }
        if (-not (Test-Path $resolved)) {
            Write-WARN "broken link in $($file.FullName.Replace($VaultPath, '').TrimStart('\','/')): $link"
            $missingLinks++
        }
    }
}

if ($missingLinks -eq 0) {
    Write-OK "no broken wiki/relative links detected"
    $issues += @{ check = "broken_links"; status = "ok" }
} else {
    Write-ERR "broken links detected: $missingLinks"
    $issues += @{ check = "broken_links"; status = "error"; count = $missingLinks }
    $exitCode = 1
}

$rawLinks = 0
$missingRaw = 0
foreach ($file in $wikiFiles) {
    $content = Get-Content -Path $file.FullName -Raw
    $matches = [regex]::Matches($content, '\[[^\[\]]+\]\(([^)]+)\)')
    foreach ($match in $matches) {
        $link = $match.Groups[1].Value
        if ($link -notlike '../../raw/*') { continue }
        $rawLinks++
        $resolved = Join-Path $VaultPath $link.TrimStart('\','/')
        if (-not (Test-Path $resolved)) {
            Write-WARN "missing raw source in $($file.Name): $link"
            $missingRaw++
        }
    }
}

Write-OK "wiki->raw links checked: $rawLinks"
if ($missingRaw -eq 0) {
    Write-OK "no missing raw sources detected"
    $issues += @{ check = "raw_links"; status = "ok" }
} else {
    Write-ERR "missing raw sources detected: $missingRaw"
    $issues += @{ check = "raw_links"; status = "error"; count = $missingRaw }
    $exitCode = 1
}

Write-Section "Frontmatter Completeness"
$requiredFields = @('title', 'source', 'created', 'domain')
$frontMatterTotal = 0
$frontMatterMissing = 0
foreach ($file in $wikiFiles) {
    if ($file.Name -eq 'log.md') { continue }
    $frontMatterTotal++
    $missingFields = @()
    $fileContent = Get-Content -Path $file.FullName -Raw
    foreach ($field in $requiredFields) {
        $pattern = '(?m)^\s*' + $field + ': '
        if ($fileContent -notmatch $pattern) {
            $missingFields += $field
        }
    }
    if ($missingFields.Count -gt 0) {
        Write-WARN "frontmatter missing fields in $($file.Name): $($missingFields -join ', ')"
        $frontMatterMissing++
    }
}

Write-OK "frontmatter files checked: $frontMatterTotal"
if ($frontMatterMissing -eq 0) {
    Write-OK "no frontmatter missing fields detected"
    $issues += @{ check = "frontmatter"; status = "ok" }
} else {
    Write-ERR "frontmatter missing fields detected: $frontMatterMissing"
    $issues += @{ check = "frontmatter"; status = "error"; count = $frontMatterMissing }
    $exitCode = 1
}

Write-Section "Tag Convergence"
$tagDuplicateThreshold = 2
$tagCount = @{}
foreach ($file in $wikiFiles) {
    if ($file.Name -eq 'log.md') { continue }
    $content = Get-Content -Path $file.FullName -Raw
    $matches = [regex]::Matches($content, '(?m)^\s*tags:\s*\[(.*)\]')
    foreach ($match in $matches) {
        $tagText = $match.Groups[1].Value
        $tags = $tagText -split ',' | ForEach-Object { $_.Trim().Trim('"') }
        foreach ($tag in $tags) {
            if ([string]::IsNullOrWhiteSpace($tag)) { continue }
            if ($tagCount[$tag] -eq $null) {
                $tagCount[$tag] = 1
            } else {
                $tagCount[$tag] = $tagCount[$tag] + 1
            }
        }
    }
}
$tagDuplicates = 0
foreach ($tag in $tagCount.Keys) {
    $count = $tagCount[$tag]
    if ($count -gt $tagDuplicateThreshold) {
        Write-WARN "tag appears in multiple files: $tag ($count)"
        $tagDuplicates++
    }
}
if ($tagDuplicates -eq 0) {
    Write-OK "no excessive tag duplicates detected"
    $issues += @{ check = "tag_duplicates"; status = "ok" }
} else {
    Write-ERR "excessive tag duplicates detected: $tagDuplicates"
    $issues += @{ check = "tag_duplicates"; status = "error"; count = $tagDuplicates }
    $exitCode = 1
}

if ($JsonMode -eq '1') {
    $report = @{
        vault = $VaultPath
        issues = $issues
        exitCode = $exitCode
    } | ConvertTo-Json -Depth 4
    Write-Host $report
}

exit $exitCode
