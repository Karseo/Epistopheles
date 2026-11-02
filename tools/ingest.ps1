# EPISTO Ingest-Pipeline
# Liest alle Buecher unter !Episto\reader\<Autor>\<Buch>\quelle\*.md,
# zerlegt sie absatzweise in Chunks (<= Embedding-Context), vektorisiert
# sie via Ollama (mxbai-embed-large, 1024 dims) und schreibt sie in die
# Qdrant-Collection.
#
# Aufruf:
#   .\ingest.ps1                    # alle Buecher (inkrementell: haengt an)
#   .\ingest.ps1 -Reset             # Collection neu aufbauen
#   .\ingest.ps1 -Buch "D:\...\reader\<Autor>\<Buch>"   # nur ein Buch anhaengen
#   .\ingest.ps1 -Collection episto -Limit 5
#
# Chunks, die den Kontext des Embedding-Modells sprengen (mxbai-embed-large: 512
# Tokens), werden NICHT mehr still abgeschnitten, sondern geteilt (siehe
# Get-EmbeddingsPassend). Frueher fehlten so im Mittel ~19 % des Chunktexts im Vektor.
#
# Die Vektoren liegen NICHT im Archiv (!Episto\ ist Markdown+Prompts); sie
# entstehen hier als regenerierbarer Index in Qdrant.

param(
    [string]$Collection = "episto",
    [switch]$Reset,
    [int]$Limit = 0,
    [string]$Buch = ""
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# Siehe straenge.ps1: PowerShell 5.1 liest .ps1 ohne BOM ueber die
# System-Codepage, wodurch im Skripttext eingebettete Sonderzeichen wie "›"
# schon beim Parsen kaputtgehen (â€º in der Ausgabe). Fix: per Codepoint bauen.
$RANGL = [char]0x203A   # ›

$root = "d:\Workspace\!Episto"
$qdrant = "http://127.0.0.1:6333"
$ollamaEmbed = "http://127.0.0.1:11434/api/embed"
$embedModel = "mxbai-embed-large"
$dim = 1024
$wordsPerChunk = 250
$batchSize = 16

# Windows PowerShell 5.1 kodiert einen als String uebergebenen -Body NICHT als
# UTF-8, sondern ueber die System-Codepage — Umlaute/ß/Gedankenstriche werden
# dabei zu kaputten Byte-Sequenzen, Ollama/Qdrant lehnen das kaputte JSON dann
# ab ("invalid character '…' after object key:value pair"). Fix: Body explizit
# als UTF-8-Bytes senden, Encoding im Content-Type-Header mitgeben.
#
# Zusaetzlich: Invoke-RestMethod raet die Kodierung der ANTWORT aus dem
# Content-Type-Header. Qdrant liefert nur "application/json" ohne "charset" -
# PowerShell 5.1 faellt dann auf ISO-8859-1 zurueck und zerlegt UTF-8-Zeichen
# (ü, ß, –, ›) in "Ã¼"/"â€º" etc. (sichtbar z.B. in suche.ps1). Fix: Antwort-
# Bytes selbst als UTF-8 dekodieren statt der automatischen Erkennung zu
# vertrauen.
function Invoke-JsonPost([string]$Uri, $BodyObj, [string]$Method = "Post", [int]$Depth = 8, [int]$TimeoutSec = 300, [int]$Retries = 5) {
    # Ollamas interner Runner-Prozess (und gelegentlich Qdrant) lehnt unter
    # Dauerlast vereinzelt eine einzelne Verbindung ab ("connectex"-Fehler),
    # obwohl der Server unmittelbar danach wieder normal antwortet - ohne
    # Retry riss das bislang den gesamten mehrstuendigen Ingest-Lauf ab.
    $json  = $BodyObj | ConvertTo-Json -Depth $Depth
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
    for ($versuch = 1; $versuch -le $Retries; $versuch++) {
        try {
            $resp = Invoke-WebRequest -Uri $Uri -Method $Method -Body $bytes `
                -ContentType "application/json; charset=utf-8" -TimeoutSec $TimeoutSec -UseBasicParsing
            $text = [System.Text.Encoding]::UTF8.GetString($resp.RawContentStream.ToArray())
            return $text | ConvertFrom-Json
        } catch {
            # Client-Fehler (4xx, z.B. "Eingabe zu lang"): Wiederholen ist sinnlos.
            # Ausnahme: Unter Dauerlast meldet Ollama vereinzelte Verbindungsfehler
            # zwischen Server und Runner ("connectex ... Socketadresse nur einmal
            # verwendet") faelschlich als HTTP 400 - die klappen beim Wiederholen.
            $status = $null
            if ($_.Exception.Response) { $status = [int]$_.Exception.Response.StatusCode }
            if ($status -ge 400 -and $status -lt 500 -and (Get-FehlerText $_) -notmatch 'connectex|dial tcp') { throw }
            if ($versuch -ge $Retries) { throw }
            $wartezeit = 2 * $versuch
            Write-Output "  [RETRY $versuch/$Retries] $Uri : $($_.Exception.Message) - warte ${wartezeit}s"
            Start-Sleep -Seconds $wartezeit
        }
    }
}

# Text der Fehlerantwort (PowerShell 5.1: ErrorDetails oder Antwortstrom).
function Get-FehlerText($Err) {
    if ($Err.ErrorDetails -and $Err.ErrorDetails.Message) { return [string]$Err.ErrorDetails.Message }
    try {
        $sr = New-Object System.IO.StreamReader($Err.Exception.Response.GetResponseStream(), [System.Text.Encoding]::UTF8)
        return $sr.ReadToEnd()
    } catch { return [string]$Err.Exception.Message }
}

# Teilt einen Text nahe der Mitte: bevorzugt am Absatz-, dann am Satz-, dann am
# Wortende; als letzter Ausweg mitten im Text. Gibt zwei nicht leere Teile zurueck
# oder $null, wenn der Text nicht weiter teilbar ist.
function Split-Haelfte([string]$text) {
    foreach ($muster in '\n\n+', '(?<=[.!?\u2026])\s+', '\s+') {
        $stellen = [regex]::Matches($text, $muster)
        if ($stellen.Count -eq 0) { continue }
        $mitte = $text.Length / 2
        $beste = $null; $bestAbstand = [double]::MaxValue
        foreach ($m in $stellen) {
            $abstand = [Math]::Abs(($m.Index + $m.Index + $m.Length) / 2 - $mitte)
            if ($abstand -lt $bestAbstand) { $bestAbstand = $abstand; $beste = $m }
        }
        $a = $text.Substring(0, $beste.Index).Trim()
        $b = $text.Substring($beste.Index + $beste.Length).Trim()
        if ($a -ne "" -and $b -ne "") { return @($a, $b) }
    }
    if ($text.Length -ge 2) {
        $h = [int][Math]::Floor($text.Length / 2)
        return @($text.Substring(0, $h), $text.Substring($h))
    }
    return $null
}

# Embeddet Chunks mit truncate=false (Ollama kuerzt sonst STILL auf den Kontext des
# Modells) und gibt Paare (Text, Vektor) in Reihenfolge zurueck. Chunks, die den
# Kontext sprengen, werden geteilt, bis sie passen; es geht kein Text verloren.
function Get-EmbeddingsPassend([string[]]$Chunks) {
    try {
        $er = Invoke-JsonPost -Uri $ollamaEmbed -BodyObj @{ model = $embedModel; input = @($Chunks); truncate = $false } -Depth 4 -TimeoutSec 300
        $paare = @()
        for ($k = 0; $k -lt $Chunks.Count; $k++) {
            $paare += [pscustomobject]@{ Text = $Chunks[$k]; Vektor = @($er.embeddings[$k]) }
        }
        return $paare
    } catch {
        if ((Get-FehlerText $_) -notmatch 'exceeds the context length') { throw }
        if ($Chunks.Count -gt 1) {
            $mitte = [int][Math]::Floor($Chunks.Count / 2)
            return @(Get-EmbeddingsPassend @($Chunks[0..($mitte - 1)])) + @(Get-EmbeddingsPassend @($Chunks[$mitte..($Chunks.Count - 1)]))
        }
        $teile = Split-Haelfte $Chunks[0]
        if ($null -eq $teile) { throw }
        return @(Get-EmbeddingsPassend @($teile))
    }
}

function Ensure-Collection {
    try {
        Invoke-RestMethod -Uri "$qdrant/collections/$Collection" -Method Get -TimeoutSec 10 | Out-Null
        Write-Output "Collection '$Collection' vorhanden."
    } catch {
        $bodyObj = @{ vectors = @{ size = $dim; distance = "Cosine" } }
        Invoke-JsonPost -Uri "$qdrant/collections/$Collection" -BodyObj $bodyObj -Method Put -Depth 4 -TimeoutSec 30 | Out-Null
        Write-Output "Collection '$Collection' erstellt (dim=$dim, cosine)."
    }
}

if ($Reset) {
    try { Invoke-RestMethod -Uri "$qdrant/collections/$Collection" -Method Delete -TimeoutSec 30 | Out-Null } catch {}
}
Ensure-Collection

function Split-Chunks([string]$text) {
    $paras = @($text -split "`r?`n`r?`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" })
    $chunks = @()
    $cur = @(); $curWords = 0
    foreach ($p in $paras) {
        $w = ($p -split "\s+" | Where-Object { $_ -ne "" }).Count
        if ($curWords -gt 0 -and ($curWords + $w) -gt $wordsPerChunk) {
            $chunks += ($cur -join "`n`n")
            $cur = @(); $curWords = 0
        }
        $cur += $p
        $curWords += $w
    }
    if ($cur.Count -gt 0) { $chunks += ($cur -join "`n`n") }
    return $chunks
}

# ---- Buecher entdecken ----
$books = @()
foreach ($autorDir in Get-ChildItem -LiteralPath (Join-Path $root "reader") -Directory | Where-Object { $_.Name -ne "export-epistopheles" -and $_.Name -notmatch '^[._]' }) {
    foreach ($buchDir in Get-ChildItem -LiteralPath $autorDir.FullName -Directory) {
        if ($Buch -and $buchDir.FullName.TrimEnd('\') -ine $Buch.TrimEnd('\')) { continue }
        $quelleDir = Join-Path $buchDir.FullName "quelle"
        $metaPath = Join-Path $buchDir.FullName "meta.json"
        $kapPath  = Join-Path $buchDir.FullName "kapitel.json"
        if (Test-Path -LiteralPath $quelleDir) {
            $meta = if (Test-Path -LiteralPath $metaPath) { Get-Content -LiteralPath $metaPath -Raw -Encoding UTF8 | ConvertFrom-Json } else { $null }
            $kap  = if (Test-Path -LiteralPath $kapPath)  { Get-Content -LiteralPath $kapPath -Raw -Encoding UTF8 | ConvertFrom-Json } else { $null }
            $books += [pscustomobject]@{ Autor=$autorDir.Name; Buch=$buchDir.Name; Quelle=$quelleDir; Meta=$meta; Kapitel=$kap }
        }
    }
}
Write-Output "Buecher gefunden: $($books.Count)"

# ---- Verarbeitung ----
$nextId = 0
if (-not $Reset) {
    # Inkrementell: neue Punkte hinter dem bestehenden Bestand anhaengen.
    # Ohne dies starteten die IDs bei 0 und wuerden bestehende Punkte
    # ueberschreiben (Qdrant-Upsert bei gleicher ID).
    try {
        $colInfo = Invoke-RestMethod -Uri "$qdrant/collections/$Collection" -Method Get -TimeoutSec 10
        $nextId = [int]$colInfo.result.points_count
        Write-Output "Inkrementell: Punkt-IDs ab $nextId fortsetzen (bestehende Punkte bleiben unangetastet)."
    } catch {
        Write-Output "  [WARN] points_count nicht lesbar - starte bei 0 (nur bei leerer Collection sicher)."
    }
}
$totalChunks = 0
$geteilt = 0   # Chunks, die fuer den Kontext des Embedding-Modells geteilt werden mussten

foreach ($b in $books) {
    $pfadByNr = @{}
    if ($b.Kapitel) {
        foreach ($z in $b.Kapitel.zuordnung) { $pfadByNr[[string]$z.nr] = ($z.pfad -join " $RANGL ") }
    }
    $files = Get-ChildItem -LiteralPath $b.Quelle -Filter "*.md" | Where-Object { $_.Name -notlike "_*" -and $_.Name -ne "README.md" } | Sort-Object Name
    if ($Limit -gt 0) { $files = $files | Select-Object -First $Limit }

    Write-Output "Buch: $($b.Autor) / $($b.Buch)  ($($files.Count) Kapitel)"

    foreach ($f in $files) {
        $nr = if ($f.Name -match '^(\d+)') { [int]$Matches[1] } else { 0 }
        $text = Get-Content -LiteralPath $f.FullName -Raw -Encoding UTF8
        $chunks = @(Split-Chunks $text)
        $abschnitt = if ($pfadByNr.ContainsKey([string]$nr)) { $pfadByNr[[string]$nr] } else { "" }

        $idx = 0
        for ($i = 0; $i -lt $chunks.Count; $i += $batchSize) {
            $end = [Math]::Min($i + $batchSize - 1, $chunks.Count - 1)
            $batch = @($chunks[$i..$end])
            $paare = @(Get-EmbeddingsPassend $batch)
            $geteilt += $paare.Count - $batch.Count

            $points = @()
            foreach ($paar in $paare) {
                $points += @{
                    id = $nextId
                    vector = @($paar.Vektor)
                    payload = @{
                        buch       = $b.Buch
                        autor      = $b.Autor
                        datei      = $f.Name
                        kapitel_nr = $nr
                        abschnitt  = $abschnitt
                        chunk_idx  = $idx
                        text       = $paar.Text
                    }
                }
                $nextId++
                $idx++
            }
            $ubObj = @{ points = $points }
            Invoke-JsonPost -Uri "$qdrant/collections/$Collection/points?wait=true" -BodyObj $ubObj -Method Put -Depth 8 -TimeoutSec 120 | Out-Null
        }
        $totalChunks += $idx
    }
}

Write-Output "Fertig. Punkte gesamt: $nextId  (Chunks: $totalChunks, davon durch Teilen zusaetzlich: $geteilt)  Collection: $Collection"
