// Shared by the service worker and popup so both accept the same pages.
function isYouTubeWatchUrl(url) {
  try {
    const u = new URL(url);
    if (!/^https?:$/.test(u.protocol)) return false;
    return (u.hostname === "youtu.be" && /^\/[^/]+\/?$/.test(u.pathname)) ||
      (/^(www\.|m\.|music\.)?youtube\.com$/.test(u.hostname) &&
        u.pathname === "/watch" && Boolean(u.searchParams.get("v")));
  } catch (_) {
    return false;
  }
}

function isSoundCloudTrackUrl(url) {
  try {
    const u = new URL(url);
    if (!/^https?:$/.test(u.protocol)) return false;
    if (/^(on\.soundcloud\.com|soundcloud\.app\.goo\.gl)$/.test(u.hostname)) {
      return /^\/[^/]+\/?$/.test(u.pathname);
    }
    if (!/^(www\.|m\.)?soundcloud\.com$/.test(u.hostname)) return false;
    const parts = u.pathname.split("/").filter(Boolean);
    const reserved = new Set(["discover", "stream", "you", "search", "charts", "upload", "settings", "pages", "terms-of-use", "pro", "notifications", "messages"]);
    const collections = new Set(["sets", "tracks", "albums", "reposts", "likes", "popular-tracks", "followers", "following"]);
    return !reserved.has(parts[0]) && !collections.has(parts[1]) &&
      (parts.length === 2 || (parts.length === 3 && /^s-[\w-]+$/.test(parts[2])));
  } catch (_) {
    return false;
  }
}

function isSupportedTrackUrl(url) {
  return isYouTubeWatchUrl(url) || isSoundCloudTrackUrl(url);
}

function normalizeTrackUrl(url) {
  if (!isYouTubeWatchUrl(url)) return url;
  const u = new URL(url);
  const id = u.hostname === "youtu.be" ? u.pathname.split("/")[1] : u.searchParams.get("v");
  return `https://www.youtube.com/watch?v=${encodeURIComponent(id)}`;
}
