"""Media handling: fetching recordings, probing, and extracting audio/frames with ffmpeg.
 
Everything is written to a caller-supplied temporary directory so nothing persists
after an assessment finishes (recordings are confidential).
"""
from __future__ import annotations
 
import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
 
import numpy as np
 
AUDIO_SR = 16_000      # audio sent to the model
ANALYSIS_SR = 8_000    # audio used for signal analysis (keeps memory low for long classes)
 
 
class MediaError(RuntimeError):
    pass
 
 
def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, check=True, capture_output=True, **kw)
    except FileNotFoundError as e:
        raise MediaError("ffmpeg/ffprobe is not installed on this machine") from e
    except subprocess.CalledProcessError as e:
        tail = e.stderr.decode(errors="ignore")[-600:] if e.stderr else ""
        raise MediaError(f"{cmd[0]} failed: {tail}") from e
 
 
@dataclass
class MediaInfo:
    duration_s: float
    has_video: bool
    has_audio: bool
    width: int | None
    height: int | None
 
 
def probe(path: Path) -> MediaInfo:
    out = _run(["ffprobe", "-v", "error", "-print_format", "json",
                "-show_format", "-show_streams", str(path)]).stdout
    meta = json.loads(out)
    streams = meta.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"
                  and s.get("disposition", {}).get("attached_pic") != 1), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    duration = float(meta.get("format", {}).get("duration") or 0)
    if duration <= 0 and video:
        duration = float(video.get("duration") or 0)
    return MediaInfo(
        duration_s=duration,
        has_video=video is not None,
        has_audio=audio is not None,
        width=int(video["width"]) if video else None,
        height=int(video["height"]) if video else None,
    )
 
 
def decode_audio(path: Path) -> np.ndarray:
    """Decode to mono 8 kHz float32 in [-1, 1] for signal analysis."""
    raw = _run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1",
                "-ar", str(ANALYSIS_SR), "-f", "s16le", "-"]).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
 
 
def compress_audio(path: Path, out_dir: Path) -> Path:
    """Small mono speech-quality audio for the LLM (~15 MB per hour)."""
    out = out_dir / "audio.mp3"
    _run(["ffmpeg", "-v", "error", "-y", "-i", str(path), "-vn", "-ac", "1",
          "-ar", str(AUDIO_SR), "-b:a", "32k", str(out)])
    return out
 
 
def sample_frames(path: Path, info: MediaInfo, out_dir: Path, n: int = 12,
                  width: int = 768) -> list[tuple[float, Path]]:
    """Grab n evenly spaced screenshots (skipping the very start/end)."""
    if not info.has_video or info.duration_s <= 0:
        return []
    frames = []
    for i in range(n):
        t = info.duration_s * (i + 0.5) / n
        out = out_dir / f"frame_{i:02d}.jpg"
        try:
            _run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(path),
                  "-frames:v", "1", "-vf", f"scale={width}:-2", "-q:v", "4", str(out)])
        except MediaError:
            continue
        if out.exists() and out.stat().st_size > 0:
            frames.append((t, out))
    return frames
 
 
def low_res_frames(path: Path, w: int = 64, h: int = 36) -> tuple[np.ndarray, float]:
    """Tiny grayscale copies of the video's keyframes, for screen-activity signals.
 
    Decoding only keyframes is ~10x faster than decoding every frame, which matters
    for hour-long classes on a small CPU. Returns (frames, average seconds between them).
    """
    def grab(sync_opt: str) -> bytes:
        return _run(["ffmpeg", "-v", "error", "-skip_frame", "nokey", "-i", str(path), "-an",
                     sync_opt, "vfr", "-vf", f"scale={w}:{h},format=gray",
                     "-f", "rawvideo", "-"]).stdout
 
    # ffmpeg >= 5.1 uses -fps_mode; ffmpeg 8 removed the older -vsync spelling.
    try:
        raw = grab("-fps_mode")
    except MediaError as e:
        if "fps_mode" not in str(e):
            raise
        raw = grab("-vsync")
    if not raw:
        return np.zeros((0, h, w), dtype=np.uint8), 0.0
    frames = np.frombuffer(raw, dtype=np.uint8).reshape(-1, h, w)
    return frames, 0.0
 
 
# --------------------------------------------------------------------------- links
 
_DRIVE_ID = re.compile(r"(?:/d/|id=|/file/d/)([A-Za-z0-9_-]{20,})")
 
 
def fetch_link(url: str, out_dir: Path, max_bytes: int = 3 * 1024**3) -> Path:
    """Download a recording from a Google Drive share link or a direct media URL."""
    url = url.strip()
    if not re.match(r"^https?://", url):
        raise MediaError("Please paste a full http(s) link")
    target = out_dir / "input_from_link"
    if "drive.google.com" in url or "docs.google.com" in url:
        m = _DRIVE_ID.search(url)
        if not m:
            raise MediaError("Could not find a file id in that Google Drive link "
                             "(folder links are not supported, link the file itself)")
        import gdown
        got = gdown.download(id=m.group(1), output=str(target), quiet=True)
        if not got or not target.exists():
            raise MediaError("Google Drive refused the download. Make sure the file is "
                             "shared as 'Anyone with the link can view'.")
    else:
        import requests
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            ctype = r.headers.get("content-type", "")
            if "text/html" in ctype:
                raise MediaError("That link returns a web page, not a media file. "
                                 "Use a direct file link or a Google Drive file link.")
            size = 0
            with open(target, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    size += len(chunk)
                    if size > max_bytes:
                        raise MediaError("File is larger than 3 GB")
                    f.write(chunk)
    return target
 
 
def save_upload(uploaded, out_dir: Path) -> Path:
    """Persist a Streamlit UploadedFile into the temp dir without loading it all in memory."""
    suffix = Path(uploaded.name).suffix or ".mp4"
    target = out_dir / f"input{suffix}"
    with open(target, "wb") as f:
        shutil.copyfileobj(uploaded, f, length=1 << 20)
    return target