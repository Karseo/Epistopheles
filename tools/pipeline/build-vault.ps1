<#
.SYNOPSIS
  Baut aus uebersetzten chunk_*.md (z.B. Output von ebook-translate.py) einen
  strukturierten Obsidian-Vault: Kapitel-Anker, MOC, Register, Glossar, WikiLinks.

  Konsolidiert die frueheren FIMI-Einmalskripte (build-vault-part1..5,
  create-glossary, fix-vault-links, fix-vault-part2) zu EINEM generischen Skript.

.PARAMETER SourceDir   Ordner mit chunk_*.md (z.B. D:\Workspace\!Episto\rohdaten\Lektor\<Autor>\<Titel>)
.PARAMETER VaultPath   Ziel-Vault-Ordner (wird angelegt)
.PARAMETER Buch        Buchtitel
.PARAMETER Autor       Autor (Default: Unbekannt)
.PARAMETER Untertitel  optionaler Untertitel/Volltitel
.PARAMETER Jahr        Erscheinungsjahr (optional)
.PARAMETER Sprache     Sprachvermerk fuer Metadaten
.PARAMETER ErstesKapitel  Kapitelname fuer Chunks vor der ersten Ueberschrift
.PARAMETER MinGlossar  Mindest-Vorkommen fuer eine eigene Glossar-Notiz (Default 3)

.EXAMPLE
  .\build-vault.ps1 -SourceDir "D:\Workspace\!Episto\rohdaten\Lektor\Scott Horton\Provoked" `
                    -VaultPath "D:\Obsidian\LokalVault\Provoked" `
                    -Buch "Provoked" -Autor "Scott Horton" -Jahr 2024 `
                    -Untertitel "How Washington Started the New Cold War..."
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$SourceDir,
    [Parameter(Mandatory)][string]$VaultPath,
    [Parameter(Mandatory)][string]$Buch,
    [string]$Autor = "Unbekannt",
    [string]$Untertitel = "",
    [string]$Jahr = "",
    [string]$Sprache = "Deutsch (maschinell uebersetzt)",
    [string]$ErstesKapitel = "Vorwort und Einleitung",
    [int]$MinGlossar = 3
)

$ErrorActionPreference = "Stop"
$Utf8NoBom = [System.Text.UTF8Encoding]::new($false)

function Get-SafeName([string]$name) {
    return ($name -replace '[\\/:*?"<>|]', ' ').Trim()
}
function Write-Utf8([string]$path, [string[]]$lines) {
    [System.IO.File]::WriteAllLines($path, $lines, $Utf8NoBom)
}

# -- Setup ----------------------------------------------------------------------
$notesDir = Join-Path $VaultPath "Notizen"
$glossDir = Join-Path $notesDir "Glossar"
New-Item -ItemType Directory -Force -Path $glossDir | Out-Null
$bookTag   = ($Buch.ToLowerInvariant() -replace '[^a-z0-9]+', '-').Trim('-')
$titelVoll = if ($Untertitel) { "$Buch - $Untertitel" } else { $Buch }

Write-Host "=== build-vault: $Buch ===" -ForegroundColor Cyan
Write-Host "Quelle: $SourceDir"
Write-Host "Vault:  $VaultPath"

# -- 1. Chunks in den Vault kopieren --------------------------------------------
$srcFiles = Get-ChildItem (Join-Path $SourceDir "chunk_*.md") -File -EA SilentlyContinue | Sort-Object Name
if (-not $srcFiles) { throw "Keine chunk_*.md in '$SourceDir' gefunden." }
foreach ($f in $srcFiles) { Copy-Item $f.FullName (Join-Path $notesDir $f.Name) -Force }
$files = Get-ChildItem (Join-Path $notesDir "chunk_*.md") -File | Sort-Object Name
Write-Host "Chunks kopiert: $($files.Count)"

# -- 2. Kapitel-Map + Reihenfolge (aus ##-Ueberschriften) -----------------------
# chapterMap[chunk] = Kapitel der letzten ##-Ueberschrift im Chunk (sonst geerbt).
$chapterMap = @{}
$currentChapter = $ErstesKapitel
foreach ($f in $files) {
    $content = Get-Content $f.FullName -Raw -Encoding UTF8
    foreach ($h in [regex]::Matches($content, '^## (.+)$', 'Multiline')) {
        $currentChapter = ($h.Groups[1].Value.Trim() -replace '\{[^}]*\}\s*$', '').Trim()
    }
    $chapterMap[$f.Name] = $currentChapter
}
# Reihenfolge = distinkte Ueberschriften in Lesereihenfolge
$chapterOrder = @()
$current = ""
foreach ($f in $files) {
    $content = Get-Content $f.FullName -Raw -Encoding UTF8
    foreach ($h in [regex]::Matches($content, '^## (.+)$', 'Multiline')) {
        $title = ($h.Groups[1].Value.Trim() -replace '\{[^}]*\}\s*$', '').Trim()
        if ($title -and $title -ne $current) { $chapterOrder += $title; $current = $title }
    }
}
if ($files.Count -gt 0 -and ($chapterOrder.Count -eq 0 -or $chapterMap[$files[0].Name] -ne $chapterOrder[0])) {
    $chapterOrder = @($chapterMap[$files[0].Name]) + $chapterOrder
}
Write-Host "Kapitel: $($chapterOrder.Count)"

# Kapitel -> Safe-Dateiname
$chapterToSafeFile = @{}
foreach ($ch in $chapterOrder) { $chapterToSafeFile[$ch] = "Kapitel: $(Get-SafeName $ch)" }

# -- 3. Glossar-Terme sammeln (einmal, mit Kapitel-Zuordnung) --------------------
# Terme = eckig geklammerter Text, der KEIN Markdown-Link ist:  [Begriff]
$glossaryTerms = @{}   # term -> @{ count; chapters = @{ kapitel = n } }
foreach ($f in $files) {
    $content = Get-Content $f.FullName -Raw -Encoding UTF8
    foreach ($m in [regex]::Matches($content, '(?<!\()\[([^\[\]]+)\](?!\(|\[)')) {
        $term = $m.Groups[1].Value.Trim()
        if ($term.Length -le 1) { continue }
        if (-not $glossaryTerms.ContainsKey($term)) { $glossaryTerms[$term] = @{ count = 0; chapters = @{} } }
        $glossaryTerms[$term].count++
        $ch = $chapterMap[$f.Name]
        if (-not $glossaryTerms[$term].chapters.ContainsKey($ch)) { $glossaryTerms[$term].chapters[$ch] = 0 }
        $glossaryTerms[$term].chapters[$ch]++
    }
}
Write-Host "Glossar-Terme (gesamt): $($glossaryTerms.Count)"

# -- 4. Kapitel-Anker-Notizen ---------------------------------------------------
$anchorCount = 0
foreach ($ch in $chapterOrder) {
    $refs = @()
    foreach ($f in $files) { if ($chapterMap[$f.Name] -eq $ch) { $refs += "- [[Notizen/$($f.Name -replace '\.md$','')]]" } }
    $out = @("---", "type: chapter", "title: $ch", "tags: [kapitel, $bookTag]", "---", "", "# $ch", "", "## Enthaltene Notizen", "") + $refs
    Write-Utf8 (Join-Path $notesDir "$(Get-SafeName "Kapitel: $ch").md") $out
    $anchorCount++
}
Write-Host "Kapitel-Anker-Notizen: $anchorCount"

# -- 5. MOC.md + Ueber das Buch.md ----------------------------------------------
$moc = [System.Collections.Generic.List[string]]::new()
"---", "type: MOC", "title: $Buch - Inhaltsverzeichnis", "---", "", "# $titelVoll", "" | ForEach-Object { $moc.Add($_) }
$moc.Add("**Autor:** $Autor$(if ($Jahr) { " ($Jahr)" })")
$moc.Add("**Sprache:** $Sprache")
$moc.Add("**Chunks:** $($files.Count) Notizen")
$moc.Add(""); $moc.Add("## Inhaltsverzeichnis"); $moc.Add("")
$idx = 1
foreach ($ch in $chapterOrder) { $moc.Add("$idx. [[Notizen/$($chapterToSafeFile[$ch])|$ch]]"); $idx++ }
$moc.Add(""); $moc.Add("## Navigation")
$moc.Add("- [[Register|Alphabetisches Register aller Glossar-Begriffe]]")
$moc.Add("- [[Ueber das Buch|Metadaten und Kontext]]")
Write-Utf8 (Join-Path $VaultPath "MOC.md") $moc.ToArray()

$about = @(
    "---", "type: meta", "title: Ueber das Buch", "---", "",
    "# $Buch - Ueber das Buch", "",
    "| Feld | Wert |", "|------|------|",
    "| Titel | $titelVoll |", "| Autor | $Autor |", "| Jahr | $Jahr |",
    "| Sprache | $Sprache |", "| Chunks | $($files.Count) |", "| Kapitel | $($chapterOrder.Count) |", "",
    "## Struktur dieses Vaults",
    "- **MOC.md** - Inhaltsverzeichnis mit Kapitel-Navigation",
    "- **Register.md** - Alphabetisches Register aller Begriffe",
    "- **Notizen/** - Text-Chunks + Kapitel-Anker-Notizen",
    "- **Notizen/Glossar/** - Glossar-Notizen (ab $MinGlossar Vorkommen)"
)
Write-Utf8 (Join-Path $VaultPath "Ueber das Buch.md") $about
Write-Host "MOC.md + Ueber das Buch.md erstellt."

# -- 6. Register.md (alphabetisch, alle Terme) ----------------------------------
$reg = [System.Collections.Generic.List[string]]::new()
"---", "type: register", "title: $Buch - Alphabetisches Register", "---", "", "# Alphabetisches Register", "", "Alle Glossar-Begriffe. Zahl = Haeufigkeit als Verweis.", "" | ForEach-Object { $reg.Add($_) }
$curLetter = ""
foreach ($t in ($glossaryTerms.GetEnumerator() | Sort-Object Name)) {
    $fc = $t.Name.Substring(0, 1)
    if ([char]::IsLetter($fc)) {
        if ($fc -ne $curLetter) { $curLetter = $fc; $reg.Add("## $curLetter") }
        $reg.Add("- **$($t.Name)** ($($t.Value.count)x)")
    }
}
Write-Utf8 (Join-Path $VaultPath "Register.md") $reg.ToArray()
Write-Host "Register.md erstellt."

# -- 7. Glossar-Notizen fuer haeufige Terme (>= MinGlossar) ---------------------
$glossCount = 0
foreach ($t in $glossaryTerms.GetEnumerator()) {
    if ($t.Value.count -lt $MinGlossar) { continue }
    $lines = [System.Collections.Generic.List[string]]::new()
    "---", "type: glossar", "term: $($t.Key)", "occurrences: $($t.Value.count)", "tags: [glossar, $bookTag]", "---", "", "# $($t.Key)", "", "**Vorkommen:** $($t.Value.count) Mal", "", "## In folgenden Kapiteln:", "" | ForEach-Object { $lines.Add($_) }
    foreach ($ce in ($t.Value.chapters.GetEnumerator() | Sort-Object Value -Descending)) {
        $safeCh = $chapterToSafeFile[$ce.Key]
        if ($safeCh) { $lines.Add("- [[Notizen/$safeCh]] ($($ce.Value)x)") }
    }
    Write-Utf8 (Join-Path $glossDir "$(Get-SafeName $t.Key).md") $lines.ToArray()
    $glossCount++
}
Write-Host "Glossar-Notizen (>= $MinGlossar): $glossCount"

# -- 8. Calibre-Anker-Links in Chunks zu Plaintext ------------------------------
# [Text](#anchor){.calibre}  ->  Text
$calibre = 0
foreach ($f in $files) {
    $c = Get-Content $f.FullName -Raw -Encoding UTF8
    $n = $c -replace '\[([^\]]+)\]\([^)]+\)\{\.calibre\}', '$1'
    if ($n -ne $c) { $calibre += ([regex]::Matches($c, '\[([^\]]+)\]\([^)]+\)\{\.calibre\}')).Count; [System.IO.File]::WriteAllText($f.FullName, $n, $Utf8NoBom) }
}
Write-Host "Calibre-Anker entfernt: $calibre"

# -- 9. Link-/Fussnoten-Reparatur (ehem. fix-vault-links + fix-vault-part2) ------
# Glossar-Terme fuer WikiLink-Verlinkung (aus den erzeugten Glossar-Dateien)
$glossLink = @{}   # lower -> exakter Term
foreach ($gf in (Get-ChildItem $glossDir -Filter "*.md" -File -EA SilentlyContinue)) {
    $term = [System.IO.Path]::GetFileNameWithoutExtension($gf.Name)
    if ($term.Length -ge 3) { $glossLink[$term.ToLowerInvariant()] = $term }
}
$termsByLen = $glossLink.Values | Sort-Object { $_.Length } -Descending
$tocRemoved = 0; $footnotes = 0; $wikiExact = 0; $bareLinks = 0; $errors = 0

foreach ($f in $files) {
  try {
    $content = Get-Content $f.FullName -Raw -Encoding UTF8

    # 9a. Fuehrende TOC-Anker: alles zwischen Frontmatter und erster Ueberschrift verwerfen
    $out = [System.Collections.Generic.List[string]]::new()
    $inFm = $false; $hitHead = $false; $stripped = $false
    foreach ($line in ($content -split "`r?`n")) {
        if ($line.Trim() -eq '---') { $inFm = -not $inFm; $out.Add($line); continue }
        if ($inFm) { $out.Add($line); continue }
        if (-not $hitHead) {
            if ($line -match '^\s*#+\s') { $hitHead = $true; $out.Add($line) } else { $stripped = $true }
            continue
        }
        $out.Add($line)
    }
    if ($stripped) { $tocRemoved++ }
    $content = $out -join "`r`n"

    # 9b. Fussnoten: [][[N]](#..) bzw. escaped-Variante -> [^N]
    $before = $content.Length
    $content = $content -replace '\[\]\\?\[\\?\[(\d+)\]\\?\]\\?\]\(#.*?\)', '[^$1]'
    $content = $content -replace '\[\]\[\[(\d+)\]\]\(#.*?\)', '[^$1]'
    if ($content.Length -ne $before) { $footnotes++ }
    # leere [] Zeilen
    $content = $content -replace '(?m)^\s*\[\]\s*$', ''

    # 9c. Bekannte Glossar-Terme (Wortgrenze) zu WikiLinks
    foreach ($term in $termsByLen) {
        $pat = "\b$([regex]::Escape($term))\b"
        $mc = [regex]::Matches($content, $pat).Count
        if ($mc -gt 0 -and $mc -lt 100) { $content = $content -replace $pat, "[[Glossar/$term|$term]]"; $wikiExact += $mc }
    }
    # 9d. Bare [Term] -> Glossar-WikiLink falls Term bekannt
    foreach ($m in [regex]::Matches($content, '(?<!\[)\[([^\[\]]+)\](?!\(|\[)')) {
        $term = $m.Groups[1].Value.Trim()
        if ($term.Length -lt 3 -or $term.Length -gt 80) { continue }
        $lc = $term.ToLowerInvariant()
        if ($glossLink.ContainsKey($lc)) { $content = $content -replace [regex]::Escape("[$term]"), "[[Glossar/$($glossLink[$lc])|$term]]"; $bareLinks++ }
    }

    [System.IO.File]::WriteAllText($f.FullName, $content, $Utf8NoBom)
  } catch { $errors++; Write-Host "FEHLER bei $($f.Name): $_" -ForegroundColor Red }
}

Write-Host ""
Write-Host "=== Fertig ===" -ForegroundColor Green
Write-Host "TOC-Anker bereinigt:  $tocRemoved Dateien"
Write-Host "Fussnoten:            $footnotes Dateien"
Write-Host "WikiLinks (Wort):     $wikiExact"
Write-Host "WikiLinks (bare []):  $bareLinks"
Write-Host "Fehler:               $errors"
Write-Host "Vault: $VaultPath"
