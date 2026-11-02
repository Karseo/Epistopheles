# !Episto TUI - Text User Interface
# A interactive interface for the Episto System

param(
    [switch]$Debug
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# Die Hilfsskripte liegen neben diesem Skript. Aufrufe wie ".\tools\ingest.ps1"
# hingen vom aktuellen Verzeichnis ab und scheiterten, sobald das Menue nicht aus
# dem Repo-Wurzelordner gestartet wurde (z. B. aus tools\).
$ToolsDir = $PSScriptRoot

function Show-Menu {
    Clear-Host
    Write-Host "=================================================" -ForegroundColor Green
    Write-Host "            !Episto Digital Library Manager" -ForegroundColor Green
    Write-Host "=================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "1. Books list" -ForegroundColor Cyan
    Write-Host "2. Select and process book" -ForegroundColor Cyan
    Write-Host "3. Perform vectorization" -ForegroundColor Cyan
    Write-Host "4. Perform tagging" -ForegroundColor Cyan
    Write-Host "5. Generate strands" -ForegroundColor Cyan
    Write-Host "6. Check status" -ForegroundColor Cyan
    Write-Host "7. Settings" -ForegroundColor Cyan
    Write-Host "8. Search" -ForegroundColor Cyan
    Write-Host "9. Read (reader TUI)" -ForegroundColor Cyan
    Write-Host "0. Exit" -ForegroundColor Red
    Write-Host ""
    Write-Host "=================================================" -ForegroundColor Green
}

function Get-Books {
    $root = "D:\Workspace\!Episto"
    $books = @()
    
    try {
        foreach ($autorDir in Get-ChildItem -LiteralPath (Join-Path $root "reader") -Directory) {
            foreach ($buchDir in Get-ChildItem -LiteralPath $autorDir.FullName -Directory) {
                $quelleDir = Join-Path $buchDir.FullName "quelle"
                if (Test-Path -LiteralPath $quelleDir) {
                    $books += [pscustomobject]@{
                        Autor = $autorDir.Name
                        Buch = $buchDir.Name
                        Pfad = $buchDir.FullName
                    }
                }
            }
        }
    } catch {
        Write-Host "Error in book detection: $($_.Exception.Message)" -ForegroundColor Red
    }
    
    return $books
}

function Show-Books {
    Clear-Host
    Write-Host "=================================================" -ForegroundColor Green
    Write-Host "                   AVAILABLE BOOKS" -ForegroundColor Green
    Write-Host "=================================================" -ForegroundColor Green
    Write-Host ""
    
    $books = Get-Books
    
    if ($books.Count -eq 0) {
        Write-Host "No books found!" -ForegroundColor Yellow
        Read-Host "Press any key to continue..."
        return
    }
    
    for ($i = 0; $i -lt $books.Count; $i++) {
        $book = $books[$i]
        Write-Host "$($i + 1). $($book.Autor) - $($book.Buch)" -ForegroundColor White
    }
    
    Write-Host ""
    Write-Host "=================================================" -ForegroundColor Green
    Read-Host "Press any key to continue..."
}

function Select-Book {
    Clear-Host
    Write-Host "=================================================" -ForegroundColor Green
    Write-Host "                SELECT BOOK" -ForegroundColor Green
    Write-Host "=================================================" -ForegroundColor Green
    Write-Host ""
    
    $books = Get-Books
    
    if ($books.Count -eq 0) {
        Write-Host "No books found!" -ForegroundColor Red
        Read-Host "Press any key to continue..."
        return
    }
    
    for ($i = 0; $i -lt $books.Count; $i++) {
        $book = $books[$i]
        Write-Host "$($i + 1). $($book.Autor) - $($book.Buch)" -ForegroundColor White
    }
    
    Write-Host ""
    Write-Host "=================================================" -ForegroundColor Green
    
    do {
        Write-Host "Select a book (1-$($books.Count)) or 0 to cancel:" -ForegroundColor Yellow -NoNewline
        $choice = Read-Host
        $choice = [int]$choice
        
        if ($choice -eq 0) {
            return $null
        } elseif ($choice -ge 1 -and $choice -le $books.Count) {
            return $books[($choice - 1)]
        } else {
            Write-Host "Invalid selection!" -ForegroundColor Red
        }
    } while ($true)
}

function Process-Book {
    param(
        [Parameter(Mandatory=$true)][pscustomobject]$Book
    )
    
    Clear-Host
    Write-Host "=================================================" -ForegroundColor Green
    Write-Host "           PROCESS BOOK: $($Book.Autor) - $($Book.Buch)" -ForegroundColor Green
    Write-Host "=================================================" -ForegroundColor Green
    Write-Host ""
    
    $buchPfad = $Book.Pfad
    $notizenDir = Join-Path $buchPfad "notizen"
    $quelleDir = Join-Path $buchPfad "quelle"
    
    # Check if notizen directory exists
    if (-not (Test-Path -LiteralPath $notizenDir)) {
        Write-Host "Creating 'notizen' directory..." -ForegroundColor Yellow
        New-Item -ItemType Directory -Path $notizenDir -Force | Out-Null
        Write-Host "Directory created." -ForegroundColor Green
    }
    
    # Check if quelle directory exists
    if (-not (Test-Path -LiteralPath $quelleDir)) {
        Write-Host "No 'quelle' directory found!" -ForegroundColor Red
        Read-Host "Press any key to continue..."
        return
    }
    
    Write-Host "Available steps:" -ForegroundColor Cyan
    Write-Host "1. Vectorization (Ingest)" -ForegroundColor White
    Write-Host "2. Tagging" -ForegroundColor White
    Write-Host "3. Generate strands" -ForegroundColor White
    Write-Host ""
    
    do {
        Write-Host "Select a step (1-3) or 0 to cancel:" -ForegroundColor Yellow -NoNewline
        $step = Read-Host
        $step = [int]$step
        
        switch ($step) {
            1 {
                # Perform vectorization
                Write-Host "Performing vectorization..." -ForegroundColor Cyan
                & (Join-Path $ToolsDir "ingest.ps1") -Buch $buchPfad
                Write-Host "Vectorization completed." -ForegroundColor Green
                break
            }
            2 {
                # Perform tagging
                Write-Host "Performing tagging..." -ForegroundColor Cyan                
                & (Join-Path $ToolsDir "taggen.ps1") -Buch $buchPfad
                Write-Host "Tagging completed." -ForegroundColor Green
                break
            }
            3 {
                # Generate strands
                Write-Host "Generating strands..." -ForegroundColor Cyan
                & (Join-Path $ToolsDir "straenge.ps1") -Buch $buchPfad
                Write-Host "Strands generated." -ForegroundColor Green
                break
            }
            0 {
                return
            }
            default {
                Write-Host "Invalid selection!" -ForegroundColor Red
            }
        }
        
        if ($step -ne 0) {
            Read-Host "Press any key to continue..."
        }
    } while ($true)
}

function Run-Ingest {
    Clear-Host
    Write-Host "=================================================" -ForegroundColor Green
    Write-Host "                Perform vectorization" -ForegroundColor Green
    Write-Host "=================================================" -ForegroundColor Green
    Write-Host ""
    
    # ingest.ps1 ohne -Buch haengt ALLE Buecher erneut an die Collection an und
    # verdoppelt damit bereits vektorisierte (delete-by-filter ist in Qdrant
    # defekt, Duplikate gehen nur mit -Reset wieder weg). Das Menue vektorisiert
    # deshalb immer genau ein Buch. Komplett neu aufbauen: ingest.ps1 -Reset.
    $book = Select-Book
    if ($null -eq $book) {
        return
    }

    Write-Host "Running ingest process for book..." -ForegroundColor Cyan
    & (Join-Path $ToolsDir "ingest.ps1") -Buch $book.Pfad
    Write-Host "Vectorization completed." -ForegroundColor Green
    Read-Host "Press any key to continue..."
}

function Run-Reader {
    # Startet die Lese-Oberflaeche (Textual-TUI, tools\episto_tui): lesen,
    # hervorheben, kommentieren, suchen, Korrektur, Speedreader. Dieses Menue
    # bleibt dahinter offen und kehrt nach dem Beenden (q) hierher zurueck.
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) { $python = Get-Command py -ErrorAction SilentlyContinue }
    if (-not $python) {
        Write-Host "Python not found. Install Python 3 and 'pip install textual'." -ForegroundColor Red
        Read-Host "Press any key to continue..."
        return
    }

    $root = Split-Path -Parent $ToolsDir
    Push-Location $ToolsDir
    try {
        & $python.Source -m episto_tui --root $root
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Reader exited with code $LASTEXITCODE (is 'textual' installed? pip install -r episto_tui\requirements.txt)" -ForegroundColor Red
            Read-Host "Press any key to continue..."
        }
    } finally {
        Pop-Location
    }
}

function Run-Search {
    Clear-Host
    Write-Host "=================================================" -ForegroundColor Green
    Write-Host "                      SEARCH" -ForegroundColor Green
    Write-Host "=================================================" -ForegroundColor Green
    Write-Host ""

    Write-Host "Question:" -ForegroundColor Yellow -NoNewline
    $frage = Read-Host " "
    if ([string]::IsNullOrWhiteSpace($frage)) { return }

    try {
        & (Join-Path $ToolsDir "suche.ps1") -Frage $frage -Top 5
    } catch {
        Write-Host "Search error: $($_.Exception.Message)" -ForegroundColor Red
    }

    Write-Host ""
    Read-Host "Press any key to continue..."
}

function Run-Tagging {
    Clear-Host
    Write-Host "=================================================" -ForegroundColor Green
    Write-Host "                     Perform tagging" -ForegroundColor Green
    Write-Host "=================================================" -ForegroundColor Green
    Write-Host ""
    
    # List books and select one
    $book = Select-Book
    if ($null -eq $book) {
        return
    }
    
    Write-Host "Performing tagging for book..." -ForegroundColor Cyan
    & (Join-Path $ToolsDir "taggen.ps1") -Buch $book.Pfad
    Write-Host "Tagging completed." -ForegroundColor Green
    Read-Host "Press any key to continue..."
}

function Run-StrangGeneration {
    Clear-Host
    Write-Host "=================================================" -ForegroundColor Green
    Write-Host "               Generate strands" -ForegroundColor Green
    Write-Host "=================================================" -ForegroundColor Green
    Write-Host ""
    
    # List books and select one
    $book = Select-Book
    if ($null -eq $book) {
        return
    }
    
    Write-Host "Generating strands for book..." -ForegroundColor Cyan
    & (Join-Path $ToolsDir "straenge.ps1") -Buch $book.Pfad
    Write-Host "Strands generated." -ForegroundColor Green
    Read-Host "Press any key to continue..."
}

function Check-Status {
    Clear-Host
    Write-Host "=================================================" -ForegroundColor Green
    Write-Host "                   SYSTEM STATUS" -ForegroundColor Green
    Write-Host "=================================================" -ForegroundColor Green
    Write-Host ""
    
    # Check if Qdrant is running
    try {
        $qdrantStatus = Invoke-RestMethod -Uri "http://127.0.0.1:6333/cluster" -TimeoutSec 5 -ErrorAction Stop
        Write-Host "Qdrant Status: Online" -ForegroundColor Green
    } catch {
        Write-Host "Qdrant Status: Offline (Start Qdrant before continuing)" -ForegroundColor Red
    }
    
    # List books
    $books = Get-Books
    
    Write-Host ""
    Write-Host "Available books: $($books.Count)" -ForegroundColor Cyan
    if ($books.Count -gt 0) {
        for ($i = 0; $i -lt $books.Count; $i++) {
            $book = $books[$i]
            Write-Host "$($i + 1). $($book.Autor) - $($book.Buch)" -ForegroundColor White
        }
    }
    
    # Check if notizen directories exist and have content
    if ($books.Count -gt 0) {
        $book = $books[0]  # Show info for first book
        $tagsPath = Join-Path $book.Pfad "notizen\tags.json"
        $straengeDir = Join-Path $book.Pfad "notizen\straenge"
        
        if (Test-Path -LiteralPath $tagsPath) {
            $tagsJson = Get-Content -LiteralPath $tagsPath -Raw -Encoding UTF8 | ConvertFrom-Json
            Write-Host "Tags present: $($tagsJson.kapitel.Count)" -ForegroundColor Green
        } else {
            Write-Host "No tags found" -ForegroundColor Yellow
        }
        
        if (Test-Path -LiteralPath $straengeDir) {
            $straengeFiles = Get-ChildItem -LiteralPath $straengeDir -Filter "*.md" | Measure-Object
            Write-Host "Strands present: $($straengeFiles.Count)" -ForegroundColor Green
        } else {
            Write-Host "No strands found" -ForegroundColor Yellow
        }
    }
    
    Write-Host ""
    Write-Host "=================================================" -ForegroundColor Green
    Read-Host "Press any key to continue..."
}

function Show-Settings {
    Clear-Host
    Write-Host "=================================================" -ForegroundColor Green
    Write-Host "                  SETTINGS" -ForegroundColor Green
    Write-Host "=================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Current configuration:" -ForegroundColor Cyan
    Write-Host "Working directory: D:\Workspace\!Episto" -ForegroundColor White
    Write-Host "Qdrant URL: http://127.0.0.1:6333" -ForegroundColor White
    Write-Host "Embedding model: mxbai-embed-large" -ForegroundColor White
    Write-Host "Dimensions: 1024" -ForegroundColor White
    Write-Host "Chunking: Paragraph-wise (~250 words)" -ForegroundColor White
    Write-Host ""
    Write-Host "=================================================" -ForegroundColor Green
    Read-Host "Press any key to continue..."
}

# Main menu loop
do {
    Show-Menu
    Write-Host "Select an option (0-9):" -ForegroundColor Yellow -NoNewline
    $choice = Read-Host
    
    switch ($choice) {
        "1" { Show-Books }
        "2" { 
            $book = Select-Book
            if ($null -ne $book) {
                Process-Book -Book $book
            }
        }
        "3" { Run-Ingest }
        "4" { Run-Tagging }
        "5" { Run-StrangGeneration }
        "6" { Check-Status }
        "7" { Show-Settings }
        "8" { Run-Search }
        "9" { Run-Reader }
        "0" {
            Clear-Host
            Write-Host "Program stopping..." -ForegroundColor Green
            exit 0 
        }
        default { 
            Write-Host "Invalid selection!" -ForegroundColor Red
            Read-Host "Press any key to continue..."
        }
    }
} while ($true)