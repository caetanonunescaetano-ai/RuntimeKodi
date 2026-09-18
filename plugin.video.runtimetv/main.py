# -*- coding: utf-8 -*-
import sys
import json
import time
import urllib.parse
import urllib.request
import xbmcgui
import xbmcplugin

CANAIS = [
    ("Runtime TV e Filmes", "https://stream.ads.ottera.tv/playlist.m3u8?network_id=2153", "2153"),
    ("Runtime Ação", "https://stream.ads.ottera.tv/playlist.m3u8?network_id=2552", "2552"),
    ("Runtime Comédia", "https://stream.ads.ottera.tv/playlist.m3u8?network_id=2553", "2553"),
    ("Runtime Família", "https://stream.ads.ottera.tv/playlist.m3u8?network_id=5589", "5589"),
    ("Runtime Romance", "https://stream.ads.ottera.tv/playlist.m3u8?network_id=4866", "4866"),
    ("Runtime Cine Espanto", "https://stream.ads.ottera.tv/playlist.m3u8?network_id=4865", "4865"),
    ("Runtime Crime", "https://stream.ads.ottera.tv/playlist.m3u8?network_id=4864", "4864")
]

def get_epg_info(net_id):
    url = f"https://cdn.ottera.tv/channels/{net_id}/epg.json"
    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=3) as response:
            data = json.loads(response.read().decode("utf-8"))
            programs = data.get("programs", []) or data.get("epg", []) or []
            
            now_ts = int(time.time())
            current_title = ""
            next_title = ""

            for i, p in enumerate(programs):
                start = p.get("start_time") or p.get("start") or 0
                end = p.get("end_time") or p.get("end") or 0
                if start <= now_ts <= end:
                    current_title = p.get("title", "")
                    if i + 1 < len(programs):
                        next_title = programs[i + 1].get("title", "")
                    break

            if current_title:
                if next_title:
                    return f"NO AR: {current_title}\nA SEGUIR: {next_title}"
                return f"NO AR: {current_title}"
    except Exception:
        pass
    return "Sem informação de guia"

def main():
    if len(sys.argv) < 2:
        return

    handle = int(sys.argv[1])
    base_url = sys.argv[0]
    paramstring = sys.argv[2] if len(sys.argv) > 2 else ""
    params = dict(urllib.parse.parse_qsl(paramstring.lstrip("?")))

    action = params.get("action")

    if action == "play":
        idx = int(params.get("id", 0))
        stream_url = CANAIS[idx][1]
        ua = "Mozilla/5.0 (X11; Linux x86_64)"
        path_url = f"{stream_url}|User-Agent={urllib.parse.quote(ua)}"
        li = xbmcgui.ListItem(path=path_url, offscreen=True)
        xbmcplugin.setResolvedUrl(handle, True, listitem=li)
    else:
        xbmcplugin.setContent(handle, "videos")
        for idx, (nome, url_canal, net_id) in enumerate(CANAIS):
            url = f"{base_url}?action=play&id={idx}"
            epg_text = get_epg_info(net_id)
            
            li = xbmcgui.ListItem(label=nome, offscreen=True)
            li.setProperty("IsPlayable", "true")
            
            # Atualiza os campos de texto do Kodi
            info_tag = li.getVideoInfoTag()
            info_tag.setTitle(nome)
            info_tag.setPlot(epg_text)
            
            xbmcplugin.addDirectoryItem(handle=handle, url=url, listitem=li, isFolder=False)
        xbmcplugin.endOfDirectory(handle)

if __name__ == "__main__":
    main()
