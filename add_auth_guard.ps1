# Adds requireAuth() to all protected HTML pages
# For pages that have a direct function call at the end of their script

$dir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Map: filename -> [ old_init_call, new_init_call ]
# We wrap the existing init call with an async IIFE that calls requireAuth first
$replacements = @{
    'news-archive.html'      = @('    loadNews();', "    (async () => { if (!await requireAuth()) return; loadNews(); })();")
    'events-calendar.html'   = @('    initCalendar();', "    (async () => { if (!await requireAuth()) return; initCalendar(); })();")
    'faculty-directory.html' = @('    loadFaculty();', "    (async () => { if (!await requireAuth()) return; loadFaculty(); })();")
    'spotlight.html'         = @('    loadSpotlight();', "    (async () => { if (!await requireAuth()) return; loadSpotlight(); })();")
}

foreach ($filename in $replacements.Keys) {
    $path = Join-Path $dir $filename
    if (-not (Test-Path $path)) { Write-Host "SKIP (not found): $filename"; continue }
    $content = Get-Content $path -Raw -Encoding UTF8
    $old = $replacements[$filename][0]
    $new = $replacements[$filename][1]
    if ($content.Contains($old)) {
        $content = $content.Replace($old, $new)
        Set-Content -Path $path -Value $content -Encoding UTF8 -NoNewline
        Write-Host "Patched: $filename"
    } else {
        Write-Host "WARN (pattern not found): $filename -> looking for: $old"
    }
}

Write-Host "Done."
