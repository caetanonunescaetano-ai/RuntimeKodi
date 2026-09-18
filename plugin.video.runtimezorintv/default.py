# -*- coding: utf-8 -*-
import sys
import os
import urllib.parse
import xbmcgui
import xbmcplugin
import xbmcaddon

addon_url = sys.argv[0]
addon_handle = int(sys.argv[1])
args = urllib.parse.parse_qs(sys.argv[2][1:])

ADDON = xbmcaddon.Addon()
ADDON_PATH = ADDON.getAddonInfo('path')
ICONS_PATH = os.path.join(ADDON_PATH, 'resources', 'media', 'icons')

CHANNELS = [
    ("RunTime Ao Vivo", "https://stream.ads.ottera.tv/playlist.m3u8?network_id=2153", "ao_vivo.jpg"),
    ("RunTime Ação", "https://stream.ads.ottera.tv/playlist.m3u8?network_id=2552", "acao.jpg"),
    ("RunTime Record News", "https://stream.ads.ottera.tv/playlist.m3u8?network_id=5431", "record news.jpg"),
    ("RunTime Comédia", "https://stream.ads.ottera.tv/playlist.m3u8?network_id=2553", "comedia.jpg"),
    ("RunTime Romance", "https://stream.ads.ottera.tv/playlist.m3u8?network_id=4866", "romance.jpg"),
    ("RunTime Família", "https://stream.ads.ottera.tv/playlist.m3u8?network_id=5589", "familia.jpg"),
    ("RunTime Cine Espanto", "https://stream.ads.ottera.tv/playlist.m3u8?network_id=4865", "cine espanto.jpg"),
    ("RunTime Crime", "https://stream.ads.ottera.tv/playlist.m3u8?network_id=4864", "crime.jpg"),
    ("RunTime Toon Goggles", "https://stream.ads.ottera.tv/playlist.m3u8?network_id=5442", "tg brasil.jpg"),
]

mode = args.get('mode', None)

if mode is None:
    for name, url, icon_file in CHANNELS:
        icon_path = os.path.join(ICONS_PATH, icon_file)
        li = xbmcgui.ListItem(label=name)
        li.setArt({'icon': icon_path, 'thumb': icon_path})
        li.setInfo('video', {'title': name, 'genre': 'Runtime TV', 'mediatype': 'video'})
        li.setProperty('IsPlayable', 'true')
        param_url = f"{addon_url}?mode=play&url={urllib.parse.quote_plus(url)}"
        xbmcplugin.addDirectoryItem(handle=addon_handle, url=param_url, listitem=li, isFolder=False)
    xbmcplugin.endOfDirectory(addon_handle)

elif mode[0] == 'play':
    play_url = args['url'][0]
    li = xbmcgui.ListItem(path=play_url)
    li.setMimeType('application/vnd.apple.mpegurl')
    li.setProperty('inputstream', 'inputstream.adaptive')
    li.setProperty('inputstream.adaptive.manifest_type', 'hls')
    li.setProperty('IsPlayable', 'true')
    xbmcplugin.setResolvedUrl(addon_handle, True, listitem=li)
