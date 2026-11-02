# EPISTO Kapitel-Tagger (generisch)
# Analysiert jedes quelle\*.md-Kapitel eines Buchordners per lokalem LLM (Ollama
# /api/chat) und schreibt strukturierte Metadaten (Thesen, Gegenpositionen,
# Kernbegriffe, Definitionen, Belege, Zusammenfassung) nach notizen\tags.json.
#
# Aufruf:
#   .\taggen.ps1 -Buch "d:\Workspace\!Episto\reader\<Autor>\<Buch>"
#   .\taggen.ps1 -Buch "..." -Limit 3 -Model "qwen3.8:27b"
#   .\taggen.ps1 -Buch "..." -MaxCtx 262144     # groesstes erlaubtes num_ctx
#
# Der Kontext (num_ctx) waechst je Kapitel automatisch (32k/64k/96k/128k/...),
# bis -MaxCtx. Passt ein Kapitel auch dort nicht hinein, wird es mit Meldung
# uebersprungen (UEBERSPRUNGEN) statt gekuerzt verarbeitet.
#
# Resume-faehig: bereits in tags.json vorhandene Dateien werden uebersprungen.

param(
    [Parameter(Mandatory=$true)][string]$Buch,
    [int]$Limit = 0,
    [string]$Model = "qwen3.8:27b",
    # Standard- und Mindestkontext (Tokens). Kapitel, die darin nicht Platz haben
    # (ab etwa 13000 Woertern), bekommen automatisch eine groessere Stufe bis
    # -MaxCtx. Wichtig: Ollama meldet eine Ueberschreitung NICHT als Fehler, es
    # kuerzt still und behaelt nur die ersten 4 Tokens und das Ende. Die
    # Anweisung im System-Prompt (Anfang) ginge verloren, das Modell antwortet
    # frei statt mit JSON (oder, schlimmer, mit Tags nur aus dem Textende).
    [int]$NumCtx = 32768,
    # Groesster erlaubter Kontext. Das Modell kann 262144; der Speicher dafuer
    # ist bei qwen3.8:27b gering (Hybrid-Architektur).
    [int]$MaxCtx = 131072
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$quelle  = Join-Path $Buch "quelle"
$notizen = Join-Path $Buch "notizen"
New-Item -ItemType Directory -Force -Path $notizen | Out-Null
$tagsPath = Join-Path $notizen "tags.json"
$metaPath = Join-Path $Buch "meta.json"

$ollamaChat = "http://127.0.0.1:11434/api/chat"

# Windows PowerShell 5.1 kodiert einen als String uebergebenen -Body NICHT als
# UTF-8, sondern ueber die System-Codepage — Umlaute/ß/Gedankenstriche werden
# dabei zu kaputten Byte-Sequenzen und Ollamas Go-JSON-Parser bricht ab
# ("invalid character '…' after object key:value pair"). Fix: Body explizit
# als UTF-8-Bytes senden, Encoding im Content-Type-Header mitgeben.
function Invoke-JsonPost([string]$Uri, $BodyObj, [int]$Depth = 8, [int]$TimeoutSec = 600) {
    $json  = $BodyObj | ConvertTo-Json -Depth $Depth
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
    return Invoke-RestMethod -Uri $Uri -Method Post -Body $bytes `
        -ContentType "application/json; charset=utf-8" -TimeoutSec $TimeoutSec
}

function ConvertFrom-RobustJson([string]$s) {
    $t = $s.Trim()
    $t = $t -replace '(?s)^```(?:json)?\s*', ''
    $t = $t -replace '(?s)\s*```$', ''
    $t = $t.Trim()
    try { return ($t | ConvertFrom-Json) } catch {
        $a = $t.IndexOf('{'); $b = $t.LastIndexOf('}')
        if ($a -ge 0 -and $b -gt $a) { return ($t.Substring($a, $b - $a + 1) | ConvertFrom-Json) }
        throw
    }
}

# Kleinster Kontext (Stufen unten), in den Kapitel + Anweisung passen; $null, wenn
# selbst $Max nicht reicht. Gemessen an einem deutschen Kapitel: 2,17 Tokens/Wort
# (frueher angenommen: 1,7) und 3,36 Zeichen/Token; hier 2,3 als Puffer fuer
# englische und Fachtexte. 3500 Tokens Reserve fuer Anweisung, Antwort, Denkphase.
function Get-Kontext([int]$Woerter, [int]$Mindest, [int]$Max) {
    $benoetigt = [int]($Woerter * 2.3) + 3500
    foreach ($stufe in 32768, 65536, 98304, 131072, 196608, 262144) {
        if ($stufe -ge [Math]::Max($benoetigt, $Mindest) -and $stufe -le $Max) { return $stufe }
    }
    return $null
}

# Zweite Sicherung neben Get-Kontext: Hat Ollama deutlich weniger Tokens gesehen,
# als der Prompt haben muesste, wurde gekuerzt (Anweisung am Anfang vermutlich weg).
function Assert-NichtGekuerzt($Antwort, [int]$PromptZeichen) {
    $gesehen = 0
    if ($Antwort.PSObject.Properties['prompt_eval_count']) { $gesehen += [int]$Antwort.prompt_eval_count }
    if ($Antwort.PSObject.Properties['prompt_eval_cached_count']) { $gesehen += [int]$Antwort.prompt_eval_cached_count }
    $erwartet = $PromptZeichen / 3.36
    if ($gesehen -gt 0 -and $gesehen -lt 0.6 * $erwartet) {
        throw ("Ollama hat den Prompt gekuerzt ({0} statt ca. {1:N0} Tokens)" -f $gesehen, $erwartet)
    }
}

$meta = if (Test-Path -LiteralPath $metaPath) { Get-Content -LiteralPath $metaPath -Raw -Encoding UTF8 | ConvertFrom-Json } else { $null }
$werkTitel = if ($meta) { $meta.titel } else { (Split-Path $Buch -Leaf) }
$werkAutor = if ($meta -and $meta.autor) { $meta.autor } else { "" }

$index = Get-Content -LiteralPath (Join-Path $quelle "_kapitel_index.json") -Raw -Encoding UTF8 | ConvertFrom-Json
$titelMap = @{}
foreach ($e in $index) { $titelMap[$e.datei] = $e.titel }

$done = @{}
if (Test-Path -LiteralPath $tagsPath) {
    foreach ($k in (Get-Content -LiteralPath $tagsPath -Raw -Encoding UTF8 | ConvertFrom-Json).kapitel) { $done[$k.datei] = $true }
}

$systemPrompt = @"
Du bist ein Assistent fuer die Analyse philosophischer Texte. Du liest einen Abschnitt aus dem Werk "$werkTitel" von $werkAutor und extrahierst strukturierte Metadaten.

Du antwortest AUSSCHLIESSLICH mit gueltigem JSON, ohne Markdown-Codeblock, ohne Erklaerung, ohne Zusatztext.

Schema:
{
  "these": ["1-3 Hauptthesen des Abschnitts als knappe, aussagekraeftige Saetze"],
  "gegen": ["Positionen oder Theorien, die der Text kritisiert oder widerlegt; leeres Array falls keine"],
  "kern": ["3-8 zentrale Kernbegriffe als einzelne Schlagworte, kleingeschrieben"],
  "def": ["Definitionen, die der Text einfuehrt oder praezisiert; leeres Array falls keine"],
  "beleg": ["Belege, Argumente oder Beispiele, die der Text anfuehrt; leeres Array falls keine"],
  "zusammenfassung": "Genau ein Satz (hoechstens 35 Woerter): WORUM es im Abschnitt geht und WIE er vorgeht (Gegenstand und Gang). Keine Thesen, Behauptungen oder Ergebnisse wiederholen - die stehen in den Thesen"
}
"@

$files = Get-ChildItem -LiteralPath $quelle -Filter "*.md" | Where-Object { $_.Name -ne "README.md" -and $_.Name -notlike "_*" } | Sort-Object Name
$todo = @()
foreach ($f in $files) { if (-not $done.ContainsKey($f.Name)) { $todo += $f } }
if ($Limit -gt 0) { $todo = $todo | Select-Object -First $Limit }

Write-Output "Werk: $werkTitel  |  Modell: $Model  |  Offene Kapitel: $($todo.Count)"

$results = @()
if (Test-Path -LiteralPath $tagsPath) { $results = @((Get-Content -LiteralPath $tagsPath -Raw -Encoding UTF8 | ConvertFrom-Json).kapitel) }

$i = 0
foreach ($f in $todo) {
    $i++
    $text = Get-Content -LiteralPath $f.FullName -Raw -Encoding UTF8
    $woerter = ($text -split "\s+" | Where-Object { $_ -ne "" }).Count
    $titel = if ($titelMap.ContainsKey($f.Name)) { $titelMap[$f.Name] } else { $f.BaseName }
    $nr = if ($f.Name -match '^(\d+)') { [int]$Matches[1] } else { 0 }

    # Kontext je Kapitel: nie raten, sondern passend waehlen oder ueberspringen
    # (siehe Kopf: Ollama kuerzt zu lange Prompts still).
    $ctx = Get-Kontext -Woerter $woerter -Mindest $NumCtx -Max $MaxCtx
    if ($null -eq $ctx) {
        Write-Output "[$i/$($todo.Count)] $($f.Name)  ($woerter W.)  UEBERSPRUNGEN: passt nicht in -MaxCtx $MaxCtx (Kapitel weiter aufteilen oder -MaxCtx erhoehen)"
        continue
    }
    if ($ctx -gt $NumCtx) {
        Write-Output "  [KONTEXT] $($f.Name): $woerter Woerter -> num_ctx $ctx"
    }

    $userPrompt = "Kapitel $nr : `"$titel`"`n`nTEXT:`n$text"

    $bodyObj = @{
        model = $Model
        messages = @(
            @{ role = "system"; content = $systemPrompt }
            @{ role = "user";   content = $userPrompt }
        )
        stream = $false
        options = @{ temperature = 0.2; num_ctx = $ctx }
    }

    $ok = $false
    for ($attempt = 1; $attempt -le 3 -and -not $ok; $attempt++) {
        try {
            $resp = Invoke-JsonPost -Uri $ollamaChat -BodyObj $bodyObj -Depth 6 -TimeoutSec 1800
            Assert-NichtGekuerzt $resp ($systemPrompt.Length + $userPrompt.Length)
            $inhalt = [string]$resp.message.content
            try { $parsed = ConvertFrom-RobustJson $inhalt } catch {
                throw ("keine verwertbare JSON-Antwort, Anfang: '{0}'" -f $inhalt.Substring(0, [Math]::Min(80, $inhalt.Length)))
            }
            $results += [ordered]@{
                datei           = $f.Name
                kapitel_nr      = $nr
                titel           = $titel
                woerter         = $woerter
                these           = @($parsed.these)
                gegen           = @($parsed.gegen)
                kern            = @($parsed.kern)
                def             = @($parsed.def)
                beleg           = @($parsed.beleg)
                zusammenfassung = [string]$parsed.zusammenfassung
            }
            $ok = $true
        } catch {
            Write-Output "  FEHLER bei $($f.Name) (Versuch $attempt): $($_.Exception.Message)"
        }
    }

    Write-Output "[$i/$($todo.Count)] $($f.Name)  ($woerter W.)  ok=$ok"

    $out = [ordered]@{
        werk     = $werkTitel
        autor    = $werkAutor
        sprache  = "de"
        eintraege = $results.Count
        erstellt = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
        kapitel  = @($results)
    }
    [System.IO.File]::WriteAllText($tagsPath, ($out | ConvertTo-Json -Depth 6), (New-Object System.Text.UTF8Encoding($false)))
}

Write-Output "Fertig. Eintraege gesamt: $($results.Count)"
