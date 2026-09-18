# -*- coding: utf-8 -*-
import sys
import json
import urllib.parse
from urllib.parse import parse_qsl

import xbmc
import xbmcgui
import xbmcplugin
import xbmcaddon

ADDON = xbmcaddon.Addon()
HANDLE = int(sys.argv[1])
BASE_URL = sys.argv[0]

ICON = ADDON.getAddonInfo('icon')
FANART = ADDON.getAddonInfo('fanart')

# Endereço-raiz do provedor SlyGuy para Pluto TV. Ele mesmo cuida da
# autenticação/sessão por dispositivo, então não brigamos mais por token
# compartilhado entre PC/celular. O catálogo mostrado depende do IP de quem
# está acessando (a própria Pluto decide a região automaticamente).
SLYGUY_ROOT = 'plugin://slyguy.pluto.tv.provider/'
SLYGUY_ADDON_ID = 'slyguy.pluto.tv.provider'


def log(msg):
    xbmc.log('[plugin.video.plutotv] {}'.format(msg), xbmc.LOGINFO)


def build_url(params):
    return BASE_URL + '?' + urllib.parse.urlencode(params)


def _slyguy_disponivel():
    payload = {
        'jsonrpc': '2.0', 'id': 1, 'method': 'Addons.GetAddonDetails',
        'params': {'addonid': SLYGUY_ADDON_ID, 'properties': ['enabled', 'installed']}
    }
    try:
        resp = json.loads(xbmc.executeJSONRPC(json.dumps(payload)))
        detalhes = resp.get('result', {}).get('addon', {})
        return bool(detalhes.get('installed')) and bool(detalhes.get('enabled'))
    except Exception as e:
        log('Falha ao checar slyguy.pluto.tv.provider: {}'.format(e))
        return False


def _listar_diretorio_slyguy(caminho):
    """Pede ao Kodi (via JSON-RPC) o conteúdo de um caminho plugin:// do
    slyguy. Retorna a lista de itens (pastas e vídeos) com título, thumb,
    plot e o caminho plugin:// de cada um."""
    payload = {
        'jsonrpc': '2.0', 'id': 1, 'method': 'Files.GetDirectory',
        'params': {
            'directory': caminho,
            'media': 'video',
            'properties': ['title', 'thumbnail', 'plot', 'file'],
        }
    }
    try:
        resp = json.loads(xbmc.executeJSONRPC(json.dumps(payload)))
        return resp.get('result', {}).get('files', []) or []
    except Exception as e:
        log('Falha ao listar {}: {}'.format(caminho, e))
        return []


def menu_principal():
    xbmcplugin.setPluginCategory(HANDLE, 'Pluto TV')
    xbmcplugin.setContent(HANDLE, 'videos')

    if not _slyguy_disponivel():
        item = xbmcgui.ListItem(
            label='O addon "SlyGuy - Pluto TV" precisa estar instalado e ativado (toque para checar de novo)')
        item.setArt({'icon': ICON, 'fanart': FANART})
        xbmcplugin.addDirectoryItem(HANDLE, build_url({'action': 'verificar'}), item, False)
        xbmcplugin.endOfDirectory(HANDLE, succeeded=True)
        return

    _listar(SLYGUY_ROOT)


def _listar(caminho):
    itens = _listar_diretorio_slyguy(caminho)

    if not itens:
        item = xbmcgui.ListItem(label='Nenhum item encontrado aqui (toque para recarregar)')
        item.setArt({'icon': ICON, 'fanart': FANART})
        xbmcplugin.addDirectoryItem(
            HANDLE, build_url({'action': 'listar', 'caminho': caminho}), item, False)
        xbmcplugin.endOfDirectory(HANDLE, succeeded=True)
        return

    for it in itens:
        titulo = it.get('label') or it.get('title') or 'Sem nome'
        caminho_item = it.get('file', '')
        eh_pasta = it.get('filetype') == 'directory'

        item = xbmcgui.ListItem(label=titulo)
        thumb = it.get('thumbnail') or ICON
        item.setArt({'icon': thumb, 'thumb': thumb, 'fanart': FANART})
        plot = it.get('plot') or ''
        item.setInfo('video', {'title': titulo, 'plot': plot, 'mediatype': 'video'})

        if eh_pasta:
            url = build_url({'action': 'listar', 'caminho': caminho_item})
            xbmcplugin.addDirectoryItem(HANDLE, url, item, True)
        else:
            item.setProperty('IsPlayable', 'true')
            url = build_url({'action': 'tocar', 'caminho': caminho_item})
            xbmcplugin.addDirectoryItem(HANDLE, url, item, False)

    xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_LABEL_IGNORE_THE)
    xbmcplugin.endOfDirectory(HANDLE, succeeded=True)


def tocar(caminho_slyguy):
    # Repassa direto pro provedor SlyGuy: ele resolve autenticação, sessão
    # e o link real de stream por conta própria (por dispositivo).
    item = xbmcgui.ListItem(path=caminho_slyguy)
    item.setProperty('IsPlayable', 'true')
    xbmcplugin.setResolvedUrl(HANDLE, True, item)


def verificar():
    if _slyguy_disponivel():
        xbmcgui.Dialog().notification(
            'Pluto TV', 'SlyGuy disponível — recarregando', xbmcgui.NOTIFICATION_INFO, 3000)
    else:
        xbmcgui.Dialog().notification(
            'Pluto TV', 'Instale/ative o addon "SlyGuy - Pluto TV"', xbmcgui.NOTIFICATION_ERROR, 6000)
    xbmcplugin.endOfDirectory(HANDLE, succeeded=False)


def router():
    params = dict(parse_qsl(sys.argv[2][1:]))
    action = params.get('action')

    if not action:
        menu_principal()
    elif action == 'listar':
        _listar(params.get('caminho', SLYGUY_ROOT))
    elif action == 'tocar':
        tocar(params.get('caminho'))
    elif action == 'verificar':
        verificar()
    else:
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)


if __name__ == '__main__':
    router()
