$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Install the Python dependencies in .venv first (see README.md).'
}
$ffmpegDir = Join-Path $PSScriptRoot '.runtime\win32'
if (Test-Path -LiteralPath (Join-Path $ffmpegDir 'ffmpeg.exe')) {
    $env:PATH = "$ffmpegDir;$env:PATH"
}
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue) -or
    -not (Get-Command ffprobe -ErrorAction SilentlyContinue)) {
    throw 'FFmpeg and FFprobe are required on PATH or in .runtime\win32.'
}
& $python -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true
exit $LASTEXITCODE
