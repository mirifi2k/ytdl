#!/usr/bin/env python3
"""Parse YouTube / yt-dlp titles into artist, track, and remix/version metadata.

Noise labels such as [HQ] or (Official Audio) are stripped whether they use
parentheses or brackets. Musical versions such as (Club Remix) or [Extended Mix]
are kept and returned separately.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

try:
    from mutagen import File
except ImportError:  # pragma: no cover - optional for parse-only use
    File = None


# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

VERSION_KEYWORDS = (
    "remix",
    "rmx",
    "mix",
    "edit",
    "rework",
    "bootleg",
    "mashup",
    "mash up",
    "version",
    "dub",
    "vip",
    "extended",
    "radio edit",
    "radio mix",
    "original mix",
    "club mix",
    "club remix",
    "festival mix",
    "private mix",
    "instrumental",
    "acoustic",
    "acapella",
    "a cappella",
    "live",
    "slowed",
    "reverb",
    "nightcore",
    "sped up",
    "speed up",
    "chopped",
    "screwed",
    "remaster",
    "remastered",
)

# Bracket contents that are upload/quality noise, never part of the song identity.
# Matched against the full inner text (case-insensitive). Parentheses vs brackets
# do not matter — classification is by content.
NOISE_LABEL_PATTERNS = (
    r"official(?:\s+music)?\s+video",
    r"official\s+audio",
    r"official\s+lyric(?:s)?\s+video",
    r"official\s+visuali[sz]er",
    r"official\s+hd(?:\s+video)?",
    r"official\s+4k(?:\s+video)?",
    r"official",
    r"(?:music\s+)?video\s+oficial",
    r"audio\s+oficial",
    r"lyric(?:s)?\s+video",
    r"visuali[sz]er",
    r"music\s+video",
    r"audio\s+only",
    r"audio",
    r"video",
    r"mv",
    r"m/?v",
    r"hq(?:\s*[-+/]\s*flac)?",
    r"hd(?:\s*[-+/]\s*\d+p?)?",
    r"uhd",
    r"4k(?:\s*uhd)?",
    r"8k",
    r"1080p?",
    r"720p?",
    r"480p?",
    r"flac",
    r"wav",
    r"mp3",
    r"aac",
    r"best\s+quality",
    r"high\s+quality",
    r"hi[- ]?res(?:olution)?",
    r"audio\s+hq",
    r"hq\s+audio",
    r"explicit",
    r"clean(?:\s+version)?",
    r"lyrics?",
    r"with\s+lyrics",
    r"full\s+(?:song|track|audio|album|hd)",
    r"free\s+(?:download|dl)(?:\s*!?|\s+link)?",
    r"out\s+now",
    r"premiere",
    r"exclusive",
    r"monstercat(?:\s+(?:release|freebie|free\s+release))?",
    r"ncs\s+release",
    r"topic",
    r"vevo",
    r"lyrics?\s+on\s+screen",
    r"on\s+screen\s+lyrics?",
    r"karaoke",
    r"cover\s+art",
    r"album\s+art",
    r"\d{4}",  # bare year: (2019), [2024]
    r"\d{2,3}\s*bpm",
    r"bpm\s*\d{2,3}",
)

# Genre / promo tags commonly stuffed into brackets on upload titles.
NOISE_GENRE_PATTERNS = (
    r"dubstep",
    r"drum(?:\s*&\s*|\s+and\s+|\s+n\s+)?bass",
    r"dnb",
    r"edm",
    r"house(?:\s+music)?",
    r"techno",
    r"trance",
    r"trap",
    r"future\s+bass",
    r"electro(?:nic)?",
    r"dance",
    r"pop",
    r"hip[- ]?hop",
    r"rap",
    r"r&b",
    r"rn[bб]",
    r"soul",
    r"indie",
    r"rock",
    r"metal",
    r"jazz",
    r"funk",
    r"disco",
    r"reggae",
    r"reggaeton",
    r"latin",
    r"afrobeats?",
    r"amapiano",
    r"manele",
    r"k-?pop",
    r"j-?pop",
)

ARTIST_SEPARATORS = (
    r"\s+x\s+",
    r"\s+&\s+",
    r"\s+and\s+",
    r"\s*,\s*",
    r"\s+feat\.?\s+",
    r"\s+ft\.?\s+",
    r"\s+featuring\s+",
    r"\s+with\s+",
    r"\s+vs\.?\s+",
)

# Explicit mappings for genuinely ambiguous uploads with no conventional
# Artist - Track separator. These can be reviewed or edited as necessary.
AMBIGUOUS_YOUTUBE_TITLES = {
    "El Meneaito": ("Unknown Artist", "El Meneaito"),
    "Hai, sus paharul | Romanian Neo-Folklore Song | Official Audio": (
        "Unknown Artist",
        "Hai, sus paharul",
    ),
    "Tataee feat Cristina Tu imi spui": ("Tataee feat Cristina", "Tu imi spui"),
    "ASIA Ia Cu Tine Si Inima Mea HD": ("ASIA", "Ia Cu Tine Si Inima Mea"),
    "SHINee 샤이니 'Ring Ding Dong' MV": ("SHINee", "Ring Ding Dong"),
    "Gonna Make You Sweat (Everybody Dance Now) (Official HD Video)": (
        "C+C Music Factory",
        "Gonna Make You Sweat (Everybody Dance Now)",
    ),
    "Mr Woodnote & Lil Rhys 'Diamonds In The Dirt' feat. Eva Lazarus": (
        "Mr Woodnote & Lil Rhys feat. Eva Lazarus",
        "Diamonds In The Dirt",
    ),
    'Jay Sean "Ride it" (**official video***)': ("Jay Sean", "Ride It"),
}


# ---------------------------------------------------------------------------
# Basics
# ---------------------------------------------------------------------------

def clean_value(value: str | None) -> str:
    if not value:
        return ""

    value = value.strip()

    if value.upper() == "NA":
        return ""

    value = re.sub(r"\s+", " ", value)
    return value.strip()


def strip_yt_dlp_placeholder_prefix(value: str) -> str:
    value = clean_value(value)

    if "|||" not in value:
        return value

    parts = [clean_value(part) for part in value.split("|||")]

    non_empty = [
        part
        for part in parts
        if part and part.upper() != "NA"
    ]

    if not non_empty:
        return ""

    # In our yt-dlp serialized format, title is last.
    return non_empty[-1]


# ---------------------------------------------------------------------------
# Noise vs version classification
# ---------------------------------------------------------------------------

_NOISE_RE = re.compile(
    r"^(?:(?:" + "|".join(NOISE_LABEL_PATTERNS) + r")"
    r"(?:\s*[/|,+&]\s*|$))+|"
    r"(?:" + "|".join(NOISE_GENRE_PATTERNS) + r")$",
    re.IGNORECASE,
)

_VERSION_ANCHOR_RE = re.compile(
    r"\b(?:"
    + "|".join(
        re.escape(k) for k in sorted(VERSION_KEYWORDS, key=len, reverse=True)
    )
    + r")\b",
    re.IGNORECASE,
)


def looks_like_noise(value: str) -> bool:
    """True when bracket/suffix content is upload noise, not song identity."""
    value = clean_value(value)
    if not value:
        return True

    # Stars / emphasis around official labels: **official video***
    value = value.strip("*").strip()
    if not value:
        return True

    if _NOISE_RE.fullmatch(value):
        return True

    # Combinations like "Official Video HD", "HQ Audio", "4K Official Audio"
    tokens = re.split(r"[\s/|,+&-]+", value.lower())
    tokens = [t for t in tokens if t]
    if not tokens:
        return True

    noise_atoms = {
        "official", "music", "video", "audio", "lyric", "lyrics", "visualizer",
        "visualiser", "hq", "hd", "uhd", "4k", "8k", "1080p", "1080", "720p",
        "720", "480p", "480", "flac", "wav", "mp3", "aac", "explicit", "clean",
        "mv", "m/v", "topic", "vevo", "premiere", "exclusive", "karaoke",
        "only", "full", "song", "track", "album", "free", "download", "dl",
        "out", "now", "quality", "best", "high", "hi", "res", "resolution",
        "with", "on", "screen", "release", "monstercat", "ncs", "oficial",
    }
    if all(t in noise_atoms or t.isdigit() for t in tokens):
        # Avoid treating a lone year-like digit run we already cover, and avoid
        # classifying real words accidentally — require at least one strong cue.
        strong = {
            "official", "video", "audio", "hq", "hd", "4k", "8k", "flac",
            "lyrics", "lyric", "visualizer", "visualiser", "mv", "explicit",
            "clean", "vevo", "topic", "1080p", "720p",
        }
        return any(t in strong for t in tokens)

    return False


def looks_like_version(value: str) -> bool:
    """True when content names a mix/remix/edit (keep it)."""
    value = clean_value(value)
    if not value:
        return False

    # Never treat pure noise as a version even if a keyword overlaps oddly.
    if looks_like_noise(value):
        return False

    if _VERSION_ANCHOR_RE.search(value):
        return True

    # "Artist Name Remix" without needing other keywords beyond remix — covered.
    # Also accept trailing "Mix"/"Edit" forms already in VERSION_KEYWORDS.
    return False


# ---------------------------------------------------------------------------
# Title cleaning
# ---------------------------------------------------------------------------

_BRACKET_CHUNK_RE = re.compile(
    r"""
    (?P<prefix>\s*[-–—|/·•]*\s*)
    (?P<open>[\[\(\{【「『])
    (?P<inner>[^\]\)\}】」』]*)
    (?P<close>[\]\)\}】」』])
    """,
    re.VERBOSE,
)

_OPEN_TO_CLOSE = {
    "[": "]",
    "(": ")",
    "{": "}",
    "【": "】",
    "「": "」",
    "『": "』",
}


def _iter_bracket_spans(value: str):
    """Yield (start, end, open, inner, close) for top-level bracket groups."""
    for match in _BRACKET_CHUNK_RE.finditer(value):
        open_ch = match.group("open")
        close_ch = match.group("close")
        if _OPEN_TO_CLOSE.get(open_ch) != close_ch:
            continue
        yield (
            match.start(),
            match.end(),
            open_ch,
            match.group("inner"),
            close_ch,
        )


def strip_noise_labels(value: str) -> str:
    """Remove upload/quality noise; preserve musical version brackets."""
    value = clean_value(value)
    if not value:
        return ""

    # Asterisk-wrapped official labels: (**official video***)
    value = re.sub(
        r"\*+\s*official(?:\s+(?:music\s+)?(?:video|audio))?\s*\*+",
        "",
        value,
        flags=re.IGNORECASE,
    )

    # Standalone trailing noise phrases (no brackets).
    trailing_noise = (
        r"(?:official\s+(?:music\s+)?(?:video|audio)|"
        r"(?:lyric(?:s)?\s+)?video|visuali[sz]er|"
        r"hq(?:\s*[-+/]\s*flac)?|hd|4k|8k|1080p?|720p?|"
        r"flac|wav|with\s+lyrics|lyrics?|"
        r"free\s+(?:download|dl)|out\s+now|"
        r"audio\s+only|full\s+(?:song|track|audio))"
    )
    value = re.sub(
        rf"(?:\s*[|\-–—/·•]\s*|\s+){trailing_noise}\s*$",
        "",
        value,
        flags=re.IGNORECASE,
    )

    # Peel noise brackets anywhere; leave version / subtitle brackets alone.
    changed = True
    while changed:
        changed = False
        spans = list(_iter_bracket_spans(value))
        for start, end, _open, inner, _close in reversed(spans):
            inner_clean = clean_value(inner)
            if looks_like_noise(inner_clean):
                # Drop optional separator immediately before the bracket.
                cut = start
                while cut > 0 and value[cut - 1].isspace():
                    cut -= 1
                # Also drop a lone separator char before spaces.
                if cut > 0 and value[cut - 1] in "-–—|/·•":
                    cut -= 1
                    while cut > 0 and value[cut - 1].isspace():
                        cut -= 1
                value = (value[:cut] + " " + value[end:]).strip()
                value = re.sub(r"\s+", " ", value)
                changed = True
                break

    value = re.sub(r"\s+\(\s*\)|\s+\[\s*\]|\s+\{\s*\}", "", value)
    return re.sub(r"\s+", " ", value).strip(" -|·•/")


def clean_youtube_title(value: str) -> str:
    """Remove video/upload labels, preserving genuine remix and mix names."""
    return strip_noise_labels(value)


def normalize_title(value: str) -> str:
    value = strip_yt_dlp_placeholder_prefix(value)
    value = clean_youtube_title(value)

    value = value.replace("–", "-")
    value = value.replace("—", "-")
    value = value.replace("−", "-")
    value = value.replace("〜", "-")

    # 1-03 Artist - Track
    value = re.sub(r"^\s*\d{1,2}-\d{1,3}\s+", "", value)

    # 01 - Artist - Track / 01. Artist - Track / 01 Artist - Track
    value = re.sub(r"^\s*\d{1,3}\s*(?:[-.]\s*|\s+)", "", value)

    # Catalog-ish prefixes: ABC123 - Artist - Title (only when more dashes follow)
    value = re.sub(
        r"^\s*[A-Z]{2,}\d{2,}[A-Z]?\s*-\s+(?=.*\s-\s)",
        "",
        value,
        flags=re.IGNORECASE,
    )

    if " - " not in value and "_" in value:
        value = value.replace("_", " ")

    value = re.sub(r"\s+", " ", value)
    return value.strip()


def extract_version(track: str) -> tuple[str, str]:
    """Split a track name into (base_title, version).

    Trailing bracket groups are classified by content, not by () vs []:
    - noise → discarded
    - version keywords → returned as version
    - anything else (e.g. subtitles) → kept on the title
    """
    track = clean_value(track)
    track = strip_noise_labels(track)

    version = ""

    # Repeatedly peel trailing brackets from the end.
    while True:
        match = re.search(
            r"^(?P<base>.*?)\s*(?P<open>[\[\(\{【])(?P<inner>[^\]\)\}】]*)(?P<close>[\]\)\}】])\s*$",
            track,
        )
        if not match:
            break

        open_ch = match.group("open")
        close_ch = match.group("close")
        if _OPEN_TO_CLOSE.get(open_ch) != close_ch:
            break

        base = clean_value(match.group("base"))
        suffix = clean_value(match.group("inner"))

        if looks_like_noise(suffix):
            track = base
            continue

        if looks_like_version(suffix):
            version = suffix
            track = base
            continue

        # Subtitle / alternate title — stop peeling.
        break

    # Track - Extended Mix / Track - Artist Remix (unbracketed)
    if not version:
        match = re.match(r"^(?P<base>.+?)\s+-\s+(?P<suffix>.+)$", track)
        if match:
            base = clean_value(match.group("base"))
            suffix = clean_value(match.group("suffix"))
            if looks_like_version(suffix) and not looks_like_noise(suffix):
                # Avoid eating "Artist - Title" style if base looks empty of words.
                if base and not base.isdigit():
                    track = base
                    version = suffix

    return track, version


def split_artists(artist_text: str) -> list[str]:
    artist_text = clean_value(artist_text)

    if not artist_text:
        return []

    pattern = "|".join(ARTIST_SEPARATORS)

    artists = [
        clean_value(part)
        for part in re.split(
            pattern,
            artist_text,
            flags=re.IGNORECASE,
        )
    ]

    return [artist for artist in artists if artist]


def parse_serialized_yt_dlp(value: str):
    value = clean_value(value)

    if "|||" not in value:
        return None

    parts = [clean_value(part) for part in value.split("|||")]

    while len(parts) < 3:
        parts.append("")

    artist = "" if parts[0].upper() == "NA" else parts[0]
    track = "" if parts[1].upper() == "NA" else parts[1]
    title = "" if parts[2].upper() == "NA" else parts[2]

    return artist, track, title


def parse_artist_track(title: str):
    title = normalize_title(title)

    match = re.match(r"^(.+?)\s+-\s+(.+)$", title)

    if not match:
        return None

    artist_text = clean_value(match.group(1))
    remainder = clean_value(match.group(2))

    if not artist_text or not remainder:
        return None

    # Prefer the last " - " split when the right side still looks like
    # "Something - Version" that is NOT a version (rare), but if middle
    # segments are version-like keep first artist + rest as track.
    # Example: Artist - Track - Club Remix already handled in extract_version.
    artists = split_artists(artist_text)
    track, version = extract_version(remainder)

    if not track:
        return None

    return artists, track, version


def sanitize_filename(value: str) -> str:
    value = clean_value(value)

    value = value.replace("/", " - ")
    value = re.sub(r'[:*?"<>|]', "", value)
    value = re.sub(r"\s+", " ", value)

    return value.strip(" .")


def final_track_name(track: str, version: str) -> str:
    if version:
        return f"{track} ({version})"
    return track


def parse_fallback_title(title: str):
    """Try safe alternative separators and known ambiguous YouTube uploads."""
    title = strip_yt_dlp_placeholder_prefix(title)
    key = re.sub(r"\s+", " ", title).strip().casefold()
    for raw, (artist, track) in AMBIGUOUS_YOUTUBE_TITLES.items():
        if re.sub(r"\s+", " ", raw).strip().casefold() == key:
            base, version = extract_version(track)
            return split_artists(artist), base, version

    title = normalize_title(title)

    # No-space hyphens: 2pac-Ghetto Gospel, Rafaga-Mentirosa
    match = re.match(r"^(.+?)\s*-\s*(.+)$", title)
    if match:
        artist, track = map(clean_value, match.groups())
        if artist and track and not artist.isdigit():
            base, version = extract_version(track)
            artist = re.sub(r"(?i)\b(feat\.?|ft\.?)(?=[^\s])", r"\1 ", artist)
            return split_artists(artist), base, version

    # Artist 'Track' / Artist "Track"
    match = re.match(r"^(.+?)\s+['\"](.+?)['\"](?:\s+MV)?$", title, re.I)
    if match:
        artist, track = map(clean_value, match.groups())
        base, version = extract_version(track)
        return split_artists(artist), base, version

    # Title by Artist  /  "Title" by Artist
    match = re.match(r"^(.+?)\s+by\s+(.+)$", title, re.I)
    if match:
        track, artist = map(clean_value, match.groups())
        track = track.strip("\"'“”‘’")
        if track and artist and not looks_like_version(artist):
            base, version = extract_version(track)
            return split_artists(artist), base, version

    # Artist: Title
    match = re.match(r"^(.+?)\s*:\s+(.+)$", title)
    if match:
        artist, track = map(clean_value, match.groups())
        if artist and track and len(artist) <= 80:
            base, version = extract_version(track)
            return split_artists(artist), base, version

    return None


def parse_special_title_formats(title: str):
    title = normalize_title(title)

    # Track ❌ Artist Remix ❌
    match = re.match(
        r"^\s*(.+?)\s*❌\s*(.+?)\s+Remix\s*❌?\s*$",
        title,
        flags=re.IGNORECASE,
    )
    if match:
        track = clean_value(match.group(1))
        remixer = clean_value(match.group(2))
        if track and remixer:
            return [remixer], track, f"{remixer} Remix"

    # Track | Artist Remix  /  Track • Artist Remix
    match = re.match(
        r"^\s*(.+?)\s*(?:\||•|·)\s*(.+?)\s+Remix\s*$",
        title,
        flags=re.IGNORECASE,
    )
    if match:
        track = clean_value(match.group(1))
        remixer = clean_value(match.group(2))
        if track and remixer:
            return [remixer], track, f"{remixer} Remix"

    # Artist — Title (en dash already normalized) handled elsewhere.

    # 「Title」Artist / Artist「Title」
    match = re.match(r"^(.+?)\s*[「『](.+?)[」』]\s*$", title)
    if match:
        left, track = map(clean_value, match.groups())
        base, version = extract_version(track)
        return split_artists(left), base, version

    match = re.match(r"^[「『](.+?)[」』]\s*(.+)$", title)
    if match:
        track, artist = map(clean_value, match.groups())
        base, version = extract_version(track)
        return split_artists(artist), base, version

    return None


class _Args:
    """Lightweight namespace for programmatic parsing."""

    def __init__(
        self,
        yt_title: str = "",
        yt_artist: str = "",
        yt_track: str = "",
        artist: str = "",
        track: str = "",
    ):
        self.yt_title = yt_title
        self.yt_artist = yt_artist
        self.yt_track = yt_track
        self.artist = artist
        self.track = track


def determine_metadata(args):
    manual_artist = clean_value(args.artist)
    manual_track = clean_value(args.track)

    raw_yt_artist = clean_value(args.yt_artist)
    raw_yt_track = clean_value(args.yt_track)
    raw_yt_title = clean_value(args.yt_title)

    yt_artist = raw_yt_artist
    yt_track = raw_yt_track
    yt_title = raw_yt_title

    # Handle the old combined yt-dlp format: Artist|||Track|||Title
    combined = None
    for value in (raw_yt_title, raw_yt_track, raw_yt_artist):
        if "|||" in value:
            combined = parse_serialized_yt_dlp(value)
            break

    if combined:
        combined_artist, combined_track, combined_title = combined
        if combined_artist:
            yt_artist = combined_artist
        if combined_track:
            yt_track = combined_track
        if combined_title:
            yt_title = combined_title
    else:
        yt_artist = strip_yt_dlp_placeholder_prefix(yt_artist)
        yt_track = strip_yt_dlp_placeholder_prefix(yt_track)
        yt_title = strip_yt_dlp_placeholder_prefix(yt_title)

    # Manual metadata wins.
    if manual_artist and manual_track:
        artists = split_artists(manual_artist)
        track, version = extract_version(manual_track)
        return artists, track, version, "manual"

    if manual_artist and yt_track:
        artists = split_artists(manual_artist)
        track, version = extract_version(yt_track)
        return artists, track, version, "manual artist + yt-dlp track"

    if manual_track and yt_artist:
        artists = split_artists(yt_artist)
        track, version = extract_version(manual_track)
        return artists, track, version, "yt-dlp artist + manual track"

    # Best case: yt-dlp actually gives us artist + track.
    if yt_artist and yt_track:
        artists = split_artists(yt_artist)
        track, version = extract_version(yt_track)
        # Still scrub noise that slipped into yt-dlp fields.
        track = strip_noise_labels(track)
        version = strip_noise_labels(version) if version else ""
        if version and looks_like_noise(version):
            version = ""
        return artists, track, version, "yt-dlp metadata"

    # Parse special title formats.
    if yt_title:
        parsed = parse_special_title_formats(yt_title)
        if parsed:
            artists, track, version = parsed
            return artists, track, version, "parsed special title"

    # Normal Artist - Track parsing.
    if yt_title:
        parsed = parse_artist_track(yt_title)
        if parsed:
            artists, track, version = parsed
            return artists, track, version, "parsed title"

    # Partial fallback.
    if yt_artist and yt_title:
        artists = split_artists(yt_artist)
        track, version = extract_version(yt_title)
        return artists, track, version, "yt-dlp artist + title fallback"

    if yt_title:
        parsed = parse_fallback_title(yt_title)
        if parsed:
            artists, track, version = parsed
            return artists, track, version, "fallback title parsing"

    raise ValueError("Could not confidently determine artist and track name.")


def parse_title(
    yt_title: str = "",
    yt_artist: str = "",
    yt_track: str = "",
    artist: str = "",
    track: str = "",
) -> dict:
    """Parse inputs into a structured result dict (for CLI dry-run / tests)."""
    args = _Args(
        yt_title=yt_title,
        yt_artist=yt_artist,
        yt_track=yt_track,
        artist=artist,
        track=track,
    )
    artists, track_name, version, source_type = determine_metadata(args)
    track_name = clean_youtube_title(track_name)
    version = clean_youtube_title(version) if version else ""
    if version and looks_like_noise(version):
        version = ""
    # If version was stripped as noise but still embedded, re-extract.
    if not version:
        track_name, version = extract_version(track_name)

    return {
        "artists": artists,
        "track": track_name,
        "version": version,
        "title": final_track_name(track_name, version),
        "source": source_type,
    }


def set_metadata(path: Path, artists: list[str], title: str) -> None:
    if File is None:
        raise RuntimeError(
            "mutagen is not installed; pip install mutagen "
            "(or use --parse-only)"
        )

    audio = File(path, easy=True)

    if audio is None:
        raise RuntimeError(f"Mutagen could not identify audio format: {path}")

    if audio.tags is None:
        try:
            audio.add_tags()
        except Exception:
            pass

    try:
        audio["artist"] = artists
        audio["title"] = [title]
        audio.save()
    except Exception:
        try:
            audio["artist"] = ["; ".join(artists)]
            audio["title"] = [title]
            audio.save()
        except Exception as exc:
            raise RuntimeError(
                f"Could not write metadata using Mutagen: {exc}"
            ) from exc


def unique_destination(path: Path) -> Path:
    if not path.exists():
        return path

    counter = 2
    while True:
        candidate = path.with_name(f"{path.stem} ({counter}){path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def _print_parse_result(result: dict) -> None:
    print("Artists:")
    for artist in result["artists"]:
        print(f"  - {artist}")
    print(f"Track  : {result['track']}")
    if result["version"]:
        print(f"Version: {result['version']}")
    print(f"Title  : {result['title']}")
    print(f"Source : {result['source']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Determine artist/track metadata from YouTube / yt-dlp titles, "
            "optionally write tags and rename the downloaded audio."
        )
    )

    parser.add_argument(
        "file",
        type=Path,
        nargs="?",
        help="Downloaded audio file (omit with --parse-only)",
    )
    parser.add_argument("--yt-title", default="", help="yt-dlp title")
    parser.add_argument("--yt-artist", default="", help="yt-dlp artist")
    parser.add_argument("--yt-track", default="", help="yt-dlp track")
    parser.add_argument("--artist", default="", help="Manual artist override")
    parser.add_argument("--track", default="", help="Manual track override")
    parser.add_argument(
        "--destination",
        type=Path,
        help="Final destination directory (required unless --parse-only)",
    )
    parser.add_argument(
        "--parse-only",
        action="store_true",
        help="Only print parsed metadata; do not tag or move files",
    )

    args = parser.parse_args(argv)

    if args.parse_only:
        if not (args.yt_title or args.yt_artist or args.yt_track or args.artist):
            print(
                "ERROR: --parse-only needs --yt-title and/or other metadata flags.",
                file=sys.stderr,
            )
            return 1
        try:
            result = parse_title(
                yt_title=args.yt_title,
                yt_artist=args.yt_artist,
                yt_track=args.yt_track,
                artist=args.artist,
                track=args.track,
            )
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            if args.yt_title:
                print(f'YouTube title: "{args.yt_title}"', file=sys.stderr)
            return 2
        _print_parse_result(result)
        return 0

    if args.file is None or args.destination is None:
        parser.error("file and --destination are required unless --parse-only")

    source = args.file.expanduser().resolve()
    destination_dir = args.destination.expanduser().resolve()

    if not source.is_file():
        print(f"ERROR: Audio file does not exist: {source}", file=sys.stderr)
        return 1

    if not destination_dir.is_dir():
        print(
            f"ERROR: Destination does not exist: {destination_dir}",
            file=sys.stderr,
        )
        return 1

    try:
        result = parse_title(
            yt_title=args.yt_title,
            yt_artist=args.yt_artist,
            yt_track=args.yt_track,
            artist=args.artist,
            track=args.track,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        if args.yt_title:
            print(f'YouTube title: "{args.yt_title}"', file=sys.stderr)
        return 2

    artists = result["artists"]
    track = result["track"]
    version = result["version"]
    final_title = result["title"]
    source_type = result["source"]

    if not artists:
        print("ERROR: No artist could be determined.", file=sys.stderr)
        return 2

    print("Artists:")
    for artist in artists:
        print(f"  - {artist}")
    print(f"Track  : {track}")
    if version:
        print(f"Version: {version}")
    print(f"Source : {source_type}")

    try:
        set_metadata(source, artists, final_title)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 3

    filename_artist = " x ".join(artists)
    safe_artist = sanitize_filename(filename_artist)
    safe_title = sanitize_filename(final_title)
    _ = safe_artist  # reserved for future Artist - Title filenames

    if not safe_title:
        print(
            "ERROR: Track title became empty after sanitization.",
            file=sys.stderr,
        )
        return 4

    destination = unique_destination(
        destination_dir / f"{safe_title}{source.suffix.lower()}"
    )

    try:
        shutil.move(str(source), str(destination))
    except Exception as exc:
        print(f"ERROR: Could not move file: {exc}", file=sys.stderr)
        return 5

    print()
    print("Saved:")
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
