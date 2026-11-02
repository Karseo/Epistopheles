# EPISTO Vektorsuche (Test-/Nutzwerkzeug)
# Fehlte bisher komplett: ingest.ps1 fuellt Qdrant, aber es gab kein Skript,
# das tatsaechlich sucht - der Feedback-Loop "einlesen -> wiederfinden" war
# damit nie end-to-end getestet. Embeddet eine Frage via Ollama und sucht die
# Top-N aehnlichsten Chunks in Qdrant.
#
# Aufruf:
#   .\suche.ps1 -Frage "Herrschaft einer organisierten Minderheit"
#   .\suche.ps1 -Frage "..." -Top 8 -Buch "The Populist Delusion"

param(
    [Parameter(Mandatory=$true)][string]$Frage,
    [int]$Top = 5,
    [string]$Collection = "episto",
    [string]$Buch = ""
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$qdrant = "http://127.0.0.1:6333"
$ollamaEmbed = "http://127.0.0.1:11434/api/embed"
$embedModel = "mxbai-embed-large"

# Siehe ingest.ps1/taggen.ps1: PowerShell 5.1 kodiert einen String-Body nicht
# als UTF-8, sondern ueber die System-Codepage. Fix: Body explizit als
# UTF-8-Bytes senden.
#
# Zusaetzlich (neu, hier relevant weil wir Text aus der ANTWORT auslesen statt
# ihn nur zu verwerfen): Invoke-RestMethod/-WebRequest raten die Kodierung der
# Antwort aus dem Content-Type-Header. Qdrant liefert nur "application/json"
# ohne "charset" - PowerShell 5.1 faellt dann auf ISO-8859-1 zurueck und
# zerlegt UTF-8-Mehrbyte-Zeichen (ü, ß, –, ›) in "Ã¼", "â€º" etc. Ollama sendet
# charset=utf-8 explizit mit, deshalb war taggen.ps1 nicht betroffen. Fix:
# Antwort-Bytes selbst als UTF-8 dekodieren statt der automatischen Erkennung
# zu vertrauen.
function Invoke-JsonPost([string]$Uri, $BodyObj, [string]$Method = "Post", [int]$Depth = 8, [int]$TimeoutSec = 60) {
    $json  = $BodyObj | ConvertTo-Json -Depth $Depth
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
    $resp  = Invoke-WebRequest -Uri $Uri -Method $Method -Body $bytes `
        -ContentType "application/json; charset=utf-8" -TimeoutSec $TimeoutSec -UseBasicParsing
    $text = [System.Text.Encoding]::UTF8.GetString($resp.RawContentStream.ToArray())
    return $text | ConvertFrom-Json
}

$ebObj = @{ model = $embedModel; input = @($Frage) }
$er = Invoke-JsonPost -Uri $ollamaEmbed -BodyObj $ebObj -Depth 4 -TimeoutSec 60
$vector = @($er.embeddings[0])

$filter = $null
if ($Buch -ne "") {
    $filter = @{ must = @(@{ key = "buch"; match = @{ value = $Buch } }) }
}

$searchObj = @{ vector = $vector; limit = $Top; with_payload = $true }
if ($filter) { $searchObj.filter = $filter }

$res = Invoke-JsonPost -Uri "$qdrant/collections/$Collection/points/search" -BodyObj $searchObj -Method Post -Depth 8 -TimeoutSec 30

Write-Output "Frage: $Frage"
Write-Output "================================================="
foreach ($p in $res.result) {
    $pl = $p.payload
    Write-Output ""
    Write-Output ("Score {0}  |  {1} - {2}  |  Kapitel {3}: {4}" -f [Math]::Round($p.score,4), $pl.autor, $pl.buch, $pl.kapitel_nr, $pl.abschnitt)
    $snippet = [string]$pl.text
    if ($snippet.Length -gt 400) { $snippet = $snippet.Substring(0,400) + "..." }
    Write-Output $snippet
}
