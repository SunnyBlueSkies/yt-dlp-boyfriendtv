# yt-dlp extractor plugin for boyfriendtv.org
#
# BoyfriendTV serves its videos through a KVS-style player. The watch page
# embeds the stream in a player config block (hlsAuto / videoUrl / CDN
# .m3u8), NOT as a plain <video> tag, which is why stock yt-dlp reports
# "Unsupported URL" on boyfriendtv pages. This extractor reads that config
# and hands yt-dlp the real HLS master playlist, so every quality variant
# becomes a selectable format.
#
# Only boyfriendtv.org is used. Any boyfriendtv.com URL is rewritten to
# .org before the page is fetched.
#
# Install / use (see README.md):
#   yt-dlp --extractor-path /path/to/boyfriendtv-ytdlp "https://www.boyfriendtv.org/videos/1273129/justcumoverme-16/"
#   yt-dlp -F "https://www.boyfriendtv.org/videos/1273129/justcumoverme-16/"
#   yt-dlp -f best "https://www.boyfriendtv.org/videos/1273129/justcumoverme-16/"

import re

from yt_dlp.extractor.common import InfoExtractor
from yt_dlp.utils import (
    ExtractorError,
    int_or_none,
    parse_iso8601,
    strip_or_none,
    traverse_obj,
    unified_timestamp,
    url_or_none,
)


class BoyfriendTVIE(InfoExtractor):
    IE_NAME = 'boyfriendtv'
    IE_DESC = 'boyfriendtv.org'
    _VALID_URL = r'https?://(?:www\.)?boyfriendtv\.(?:org|com)/(?:videos?/(?P<id>\d+)/(?P<slug>[^/?#]+)|video/(?P<slug2>[^/?#]+)/?|embed/(?P<embed_id>\d+))'
    _TESTS = [{
        'url': 'https://www.boyfriendtv.org/videos/1273129/justcumoverme-16/',
        'info_dict': {
            'id': '1273129',
            'title': 'justcumoverme (16)',
            'ext': 'mp4',
        },
        'params': {'skip_download': True},
    }]

    # Desktop headers matching a real browser. The CDN enforces Referer and
    # a modern Chrome user agent on some assets.
    _HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Sec-Ch-Ua': '"Chromium";v="155", "Google Chrome";v="155", "Not-A.Brand";v="99"',
        'Sec-Ch-Ua-Mobile': '?0',
        'Sec-Ch-Ua-Platform': '"Windows"',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Upgrade-Insecure-Requests': '1',
    }

    def _real_extract(self, url):
        # Use only boyfriendtv.org; rewrite any .com URL to .org.
        url = re.sub(r'boyfriendtv\.com', 'boyfriendtv.org', url, flags=re.IGNORECASE)
        mobj = self._match_valid_url(url)
        video_id = mobj.group('id') or mobj.group('embed_id') or mobj.group('slug2') or mobj.group('slug')

        webpage = self._download_webpage(
            url, video_id, headers=dict(self._HEADERS, Referer=url))

        # --- Stream URLs from the player config ---------------------------
        # hlsAuto: the HLS master-playlist URL. Fetching it returns a
        # #EXTM3U master playlist with one variant per quality. Do NOT
        # string-replace the _TPL_ placeholder in it: the signed key is
        # tied to that exact path and a replaced filename 403s. Let
        # _extract_m3u8_formats resolve the variants from the playlist.
        hls_auto = self._search_regex(
            r'''["']hlsAuto["']\s*:\s*["']([^"']+)["']''',
            webpage, 'hlsAuto', default=None)
        video_url = self._search_regex(
            r'''["']videoUrl["']\s*:\s*["']([^"']+)["']''',
            webpage, 'videoUrl', default=None)

        # CDN .m3u8 links embedded anywhere in the page (escaped or plain).
        cdn_m3u8 = []
        for raw in re.findall(
                r'''(https?:(?:\\/|/)[^"' ]*cdn\.boyfriendtv\.(?:org|com)[^"' ]+\.m3u8[^"' ]*)''',
                webpage):
            u = raw.replace('\\/', '/')
            if u not in cdn_m3u8:
                cdn_m3u8.append(u)

        # KVS get_file endpoint (direct mp4 or playlist).
        get_file = []
        for raw in re.findall(
                r'''(https?:(?:\\/|/)[^"' ]*boyfriendtv\.(?:org|com)/get_file/[^"' ]+)''',
                webpage):
            u = raw.replace('\\/', '/')
            if u not in get_file:
                get_file.append(u)

        # Unescape any \/ sequences yt-dlp's regexes may have captured.
        def _clean(u):
            return url_or_none(u.replace('\\/', '/')) if u else None

        hls_auto = _clean(hls_auto)
        video_url = _clean(video_url)

        formats = []
        format_ids_seen = set()

        def _add_m3u8_formats(m3u8_url, note):
            if not m3u8_url:
                return
            try:
                fmts = self._extract_m3u8_formats(
                    m3u8_url, video_id, 'mp4', m3u8_id='hls',
                    note='Downloading %s playlist' % note, fatal=False)
            except ExtractorError:
                fmts = []
            for f in fmts or []:
                fid = f.get('format_id') or f.get('url')
                if fid in format_ids_seen:
                    continue
                format_ids_seen.add(fid)
                formats.append(f)

        def _add_http_format(stream_url, format_id, height=None):
            if not stream_url:
                return
            if stream_url in format_ids_seen:
                return
            format_ids_seen.add(stream_url)
            ext = 'mp4'
            if '.m3u8' in stream_url:
                return _add_m3u8_formats(stream_url, format_id)
            formats.append({
                'url': stream_url,
                'format_id': format_id,
                'ext': ext,
                'height': height,
            })

        # Preferred: hlsAuto master playlist gives every quality variant.
        _add_m3u8_formats(hls_auto, 'HLS master')
        # Fallback: videoUrl (mp4 or m3u8), CDN m3u8, get_file.
        if not formats:
            if video_url:
                _add_http_format(video_url, 'videoUrl')
        for u in cdn_m3u8:
            if not formats:
                _add_m3u8_formats(u, 'CDN')
        for u in get_file:
            if not formats:
                _add_http_format(u, 'get_file')

        if not formats:
            # Last resort: the raw hlsAuto URL itself as a single format.
            # yt-dlp sniffs the content type, so an HLS playlist URL works
            # even though it ends in .mp4.
            if hls_auto:
                formats.append({'url': hls_auto, 'format_id': 'hlsAuto', 'ext': 'mp4'})
            elif video_url:
                formats.append({'url': video_url, 'format_id': 'videoUrl', 'ext': 'mp4'})
            else:
                raise ExtractorError(
                    'No stream URL found in the boyfriendtv page (hlsAuto / videoUrl / CDN m3u8 / get_file all empty). '
                    'The page may require a login or the player config may have changed.')

        # NOTE: yt-dlp sorts formats automatically in current versions;
        # do not call the deprecated _sort_formats().

        # --- Metadata ------------------------------------------------------
        # Prefer Open Graph, then JSON-LD VideoObject, then <title>.
        title = self._og_search_title(webpage, default=None)
        thumbnail = self._og_search_thumbnail(webpage, default=None)
        description = self._og_search_description(webpage, default=None)

        json_ld = self._search_json_ld(webpage, video_id, default={}) or {}
        if isinstance(json_ld, list):
            json_ld = next(
                (n for n in json_ld if isinstance(n, dict) and n.get('@type') == 'VideoObject'),
                json_ld[0] if json_ld else {})
        if not title:
            title = traverse_obj(json_ld, 'name')
        if not thumbnail:
            thumb = traverse_obj(json_ld, 'thumbnailUrl')
            thumbnail = thumb[0] if isinstance(thumb, list) else thumb
        if not description:
            description = traverse_obj(json_ld, 'description')

        duration = None
        dur = traverse_obj(json_ld, 'duration')
        if dur:
            duration = parse_iso8601(dur) if isinstance(dur, str) and dur.startswith('P') else int_or_none(dur)

        # Tags: btn-tag anchors, else JSON-LD keywords, else meta keywords.
        tags = []
        for t in re.findall(
                r'''<a(?=[^>]*class=["'][^"']*btn-tag[^"']*["'])(?=[^>]*href=["']/tags/[^"']*["'])[^>]*>(.*?)</a>''',
                webpage, flags=re.I | re.S):
            t = strip_or_none(re.sub(r'<[^>]+>', '', t))
            if t and t not in tags:
                tags.append(t)
        if not tags:
            kw = traverse_obj(json_ld, 'keywords')
            if isinstance(kw, str):
                tags = [strip_or_none(x) for x in kw.split(',') if strip_or_none(x)]
            elif isinstance(kw, list):
                tags = [strip_or_none(x) for x in kw if strip_or_none(x)]
        if not tags:
            meta_kw = self._html_search_meta('keywords', webpage, default=None)
            if meta_kw:
                tags = [strip_or_none(x) for x in meta_kw.split(',') if strip_or_none(x)]

        # Performers: model-card anchors, then username-wrapper spans
        # (related-model cards carry the clean name there; the anchor body
        # also holds stat numbers), then /pornstar/ anchors, then JSON-LD.
        actors = []
        for a in re.findall(
                r'''<a(?=[^>]*href=["']/(?:pornstars?/)[^"']*["'])(?=[^>]*class=["'][^"']*model-card[^"']*["'])[^>]*>(.*?)</a>''',
                webpage, flags=re.I | re.S):
            a = strip_or_none(re.sub(r'<[^>]+>', '', a))
            if a and a not in actors:
                actors.append(a)
        if not actors:
            for a in re.findall(
                    r'''<span[^>]+class=["'][^"']*username-wrapper[^"']*["'][^>]*>(.*?)</span>''',
                    webpage, flags=re.I | re.S):
                a = strip_or_none(re.sub(r'<[^>]+>', '', a))
                if a and a not in actors:
                    actors.append(a)
        if not actors:
            for a in re.findall(
                    r'''<a[^>]+href=["'][^"']*/pornstars?/[^"']*["'][^>]*>([^<]+)</a>''',
                    webpage, flags=re.I):
                a = strip_or_none(a)
                if a and a not in actors:
                    actors.append(a)
        if not actors:
            act = traverse_obj(json_ld, ('actor', ...), ('performer', ...))
            if isinstance(act, str):
                actors = [act]
            elif isinstance(act, list):
                actors = [traverse_obj(x, 'name') or x for x in act if x]

        uploader = None
        up = re.search(r'''Uploaded by:\s*(?:</[^>]+>\s*)?(?:<[^>]+>\s*)*([^<\n]+)''', webpage, flags=re.I)
        if up:
            uploader = strip_or_none(up.group(1))

        upload_date = None
        date_str = traverse_obj(json_ld, 'uploadDate') or self._html_search_meta(
            'article:published_time', webpage, default=None)
        if date_str:
            upload_date = unified_timestamp(date_str, False)

        if not title:
            title = self._html_search_regex(
                r'<title>(.*?)</title>', webpage, 'title', default=None) or video_id
            title = re.sub(r'\s*[-|]\s*BoyfriendTV.*$', '', title or '', flags=re.I).strip()
        title = (title or video_id).strip()

        return {
            'id': video_id,
            'title': title,
            'formats': formats,
            'thumbnail': thumbnail,
            'description': description,
            'tags': tags or None,
            'duration': duration,
            'upload_date': upload_date,
            'uploader': uploader,
            # Keep performers in a standard field readers already use.
            'cast': actors or None,
            'webpage_url': url,
        }
