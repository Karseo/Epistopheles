# EPISTO Strang-Aggregator (generisch)
# Aggregiert die getaggten Kapitel (notizen\tags.json) eines Buchordners zu
# kanonischen Konzept-Strängen. Die Taxonomie liest das Skript aus
# notizen\strang_taxonomie.json (je Strang: name, slug, def, triggers[]).
#
# Zugehoerigkeit basiert auf den Kernbegriffen (kern) der Kapitel, nicht auf
# blossen Erwaehnungen. Ausgabe: notizen\straenge\<slug>.md + _strang_index.json.
#
# Aufruf:
#   .\straenge.ps1 -Buch "d:\Workspace\!Episto\reader\<Autor>\<Buch>"

param(
    [Parameter(Mandatory=$true)][string]$Buch
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# Windows PowerShell 5.1 liest .ps1-Dateien ohne UTF-8-BOM ueber die
# System-Codepage ein. Sonderzeichen, die direkt als Literal im Skripttext
# stehen (z.B. "·" oder "›"), werden dadurch beim Parsen selbst schon
# kaputtkodiert - sichtbar als "Â·" / "â€º" in der erzeugten Ausgabe. Das ist
# unabhaengig vom UTF-8-Fix fuer HTTP-Bodies (der betrifft nur Daten, die aus
# JSON gelesen werden - hier geht es um Zeichen, die im Skript selbst stehen).
# Fix: solche Zeichen nicht als Literal im Quelltext verwenden, sondern per
# Unicode-Codepoint erzeugen.
$MDOT  = [char]0x00B7   # ·
$RANGL = [char]0x203A   # ›

$tagsPath   = Join-Path $Buch "notizen\tags.json"
$taxPath    = Join-Path $Buch "notizen\strang_taxonomie.json"
$kapPath    = Join-Path $Buch "kapitel.json"
$outDir     = Join-Path $Buch "notizen\straenge"

if (-not (Test-Path -LiteralPath $outDir)) {
    New-Item -ItemType Directory -Path $outDir -Force | Out-Null
}

$tags = [System.IO.File]::ReadAllText($tagsPath, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
$straenge = [System.IO.File]::ReadAllText($taxPath, [System.Text.Encoding]::UTF8) | ConvertFrom-Json

$pfadByNr = @{}
if (Test-Path -LiteralPath $kapPath) {
    $kap = [System.IO.File]::ReadAllText($kapPath, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
    foreach ($z in $kap.zuordnung) { $pfadByNr[[string]$z.nr] = ($z.pfad -join " $RANGL ") }
}

function N([string]$s) {
    $x = $s.ToLowerInvariant()
    $x = $x -replace '[ä]','ae' -replace '[ö]','oe' -replace '[ü]','ue' -replace '[ß]','ss'
    return $x
}

$results = @()
foreach ($s in $straenge) {
    $triggers = @($s.triggers | ForEach-Object { N $_ })
    $fundstellen = @()
    foreach ($k in $tags.kapitel) {
        $kernNorm = @($k.kern | ForEach-Object { N $_ })
        $hit = $false
        foreach ($kw in $kernNorm) {
            foreach ($tr in $triggers) {
                if ($kw -like "*$tr*" -or $tr -like "*$kw*") { $hit = $true; break }
            }
            if ($hit) { break }
        }
        if ($hit) {
            $fundstellen += [ordered]@{
                nr = $k.kapitel_nr
                abschnitt = if ($pfadByNr.ContainsKey([string]$k.kapitel_nr)) { $pfadByNr[[string]$k.kapitel_nr] } else { $k.titel }
                these = @($k.these)
                def = @($k.def)
            }
        }
    }
    $results += [ordered]@{
        slug = $s.slug
        name = $s.name
        definition = $s.def
        treffer = $fundstellen.Count
        kapitel = @($fundstellen)
    }
}

$indexOut = @()
foreach ($r in $results) {
    $indexOut += [ordered]@{ slug = $r.slug; name = $r.name; treffer = $r.treffer }
    $md = @"
---
strang: $($r.name)
slug: $($r.slug)
werk: $($tags.werk)
treffer: $($r.treffer)
---

# Strang: $($r.name)

$($r.definition)

## Fundstellen ($($r.treffer))

"@
    foreach ($f in $r.kapitel) {
        $md += "`n### Kapitel $($f.nr) $MDOT $($f.abschnitt)`n"
        foreach ($th in $f.these) { $md += "- $th`n" }
        foreach ($d in $f.def) { $md += "  - _Definition:_ $d`n" }
    }
    [System.IO.File]::WriteAllText((Join-Path $outDir "$($r.slug).md"), $md, (New-Object System.Text.UTF8Encoding($false)))
}

$indexJson = @{ werk = $tags.werk; autor = $tags.autor; anzahl = $results.Count; straenge = @($indexOut) }
[System.IO.File]::WriteAllText((Join-Path $outDir "_strang_index.json"), ($indexJson | ConvertTo-Json -Depth 5), (New-Object System.Text.UTF8Encoding($false)))

Write-Output "Stränge erzeugt: $($results.Count)"
$results | Sort-Object { $_.treffer } -Descending | ForEach-Object { "{0,3}  {1}" -f $_.treffer, $_.name }
