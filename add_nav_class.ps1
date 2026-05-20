$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$files = Get-ChildItem -Path $dir -Filter '*.html' -File

foreach ($f in $files) {
    $content = Get-Content $f.FullName -Raw -Encoding UTF8

    # Add nav-link-protected to nav items (only when they don't already have a class attr on the tag)
    # News link
    $content = $content -replace '<a href="news-archive\.html">', '<a href="news-archive.html" class="nav-link-protected">'
    # Events link
    $content = $content -replace '<a href="events-calendar\.html">', '<a href="events-calendar.html" class="nav-link-protected">'
    # Faculty link
    $content = $content -replace '<a href="faculty-directory\.html">', '<a href="faculty-directory.html" class="nav-link-protected">'
    # Spotlight link
    $content = $content -replace '<a href="spotlight\.html">', '<a href="spotlight.html" class="nav-link-protected">'

    # Fix double-class if already had class="active"
    $content = $content -replace 'class="nav-link-protected" class="active"', 'class="nav-link-protected active"'
    $content = $content -replace 'class="active" class="nav-link-protected"', 'class="nav-link-protected active"'

    Set-Content -Path $f.FullName -Value $content -Encoding UTF8 -NoNewline
}

Write-Host "Done patching $($files.Count) files."
