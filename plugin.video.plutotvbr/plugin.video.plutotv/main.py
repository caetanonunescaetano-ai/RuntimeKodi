# -*- coding: utf-8 -*-
import sys
import re
import os
import json
import time
import base64
import urllib.request
import urllib.parse
import urllib.error
from urllib.parse import parse_qsl
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor

import xbmc
import xbmcgui
import xbmcplugin
import xbmcaddon
import xbmcvfs

ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo('id')
HANDLE = int(sys.argv[1])
BASE_URL = sys.argv[0]

ICON = ADDON.getAddonInfo('icon')
FANART = ADDON.getAddonInfo('fanart')

# Playlist Pluto TV Brasil, mantida atualizada por terceiros a cada poucas
# horas (os links de stream trazem um token que expira, por isso não pode
# ser embutido de forma fixa no addon — precisa ser buscado periodicamente
# para sempre pegar um token válido). URL mantida ofuscada em base64.
_PLAYLIST_B64 = ('aHR0cHM6Ly9yYXcuZ2l0aHVidXNlcmNvbnRlbnQuY29tL093bmVyUGx1Z2lu'
                  'cy9wbHV0by10di1tM3UvbWFpbi9wbHV0by1saXZlLUJSLm0zdQ==')


def _playlist_url():
    return base64.b64decode(_PLAYLIST_B64).decode('utf-8')


CACHE_TTL = 4 * 3600  # 4 horas (a fonte é regerada a cada 6h)
PAGE_SIZE = 40
PROFILE_DIR = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))
CACHE_FILE = PROFILE_DIR + 'cache_playlist.json'

EXTINF_RE = re.compile(
    r'#EXTINF:-?\d+(?P<attrs>(?:\s+[a-zA-Z0-9\-]+="[^"]*")*)\s*,(?P<title>.*)'
)
ATTR_RE = re.compile(r'([a-zA-Z0-9\-]+)="([^"]*)"')


def log(msg):
    xbmc.log('[plugin.video.plutotv] {}'.format(msg), xbmc.LOGINFO)


_EPG_CACHE = {}
EPG_TTL = 15 * 60  # 15 minutos


def _formatar_hora(iso_str):
    try:
        dt = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
        dt_local = dt.astimezone()
        return dt_local.strftime('%H:%M')
    except Exception:
        return '--:--'


def _http_get(url, timeout=15):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    for enc in ('utf-8', 'latin-1'):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode('utf-8', errors='ignore')


def _obter_epg_texto(pluto_id):
    agora = time.time()
    cache = _EPG_CACHE.get(pluto_id)
    if cache and agora - cache[0] < EPG_TTL:
        return cache[1]

    texto = None
    try:
        url = 'https://api.pluto.tv/v2/channels?channelIds=' + pluto_id
        raw = _http_get(url, timeout=6)
        dados = json.loads(raw)
        if dados:
            timelines = dados[0].get('timelines', [])
            agora_dt = datetime.now(timezone.utc)
            atual = None
            proximo = None
            for item in timelines:
                try:
                    inicio = datetime.fromisoformat(item['start'].replace('Z', '+00:00'))
                    fim = datetime.fromisoformat(item['stop'].replace('Z', '+00:00'))
                except Exception:
                    continue
                titulo = (item.get('title')
                          or (item.get('episode') or {}).get('name')
                          or '')
                if inicio <= agora_dt < fim and not atual:
                    atual = (titulo, item['start'], item['stop'])
                elif inicio >= agora_dt and not proximo:
                    proximo = (titulo, item['start'])
            linhas = []
            if atual and atual[0]:
                linhas.append('Agora: {} ({} - {})'.format(
                    atual[0], _formatar_hora(atual[1]), _formatar_hora(atual[2])))
            if proximo and proximo[0]:
                linhas.append('A seguir ({}): {}'.format(
                    _formatar_hora(proximo[1]), proximo[0]))
            if linhas:
                texto = '\n'.join(linhas)
    except Exception as e:
        log('Falha ao buscar EPG de {}: {}'.format(pluto_id, e))
        texto = None

    _EPG_CACHE[pluto_id] = (agora, texto)
    return texto


def _obter_epg_em_lote(canais):
    """Busca a programação de vários canais em paralelo. Retorna {pluto_id: texto}."""
    ids = [c['tvg_id'] for c in canais if c.get('tvg_id')]
    resultado = {}
    if not ids:
        return resultado
    with ThreadPoolExecutor(max_workers=10) as executor:
        futuros = {executor.submit(_obter_epg_texto, pid): pid for pid in set(ids)}
        for futuro in futuros:
            pid = futuros[futuro]
            try:
                resultado[pid] = futuro.result()
            except Exception:
                resultado[pid] = None
    return resultado


DESCRICOES_CATEGORIA = {
    'esportes': 'Canais 24 horas de esportes: futebol, lutas, corridas e mais.',
    'filmes': 'Canais dedicados a filmes de diversos gêneros, em exibição contínua.',
    'infantil': 'Programação infantil e desenhos animados o dia todo.',
    'música': 'Canais musicais, videoclipes e karaokê.',
    'notícias': 'Canais de notícias e jornalismo ao vivo.',
    'novelas': 'Canais dedicados a novelas e dramas.',
    'comédia': 'Canais de humor, comédia e entretenimento leve.',
    'curiosidades': 'Canais de curiosidades, reality shows e histórias reais.',
    'estilo de vida': 'Canais de culinária, viagem e estilo de vida.',
    'investigação': 'Canais de investigação, crimes reais e mistérios policiais.',
    'natureza': 'Canais sobre natureza, animais e vida selvagem.',
    'mistérios e sobrenatural': 'Canais sobre mistérios, paranormal e o sobrenatural.',
    'retrô': 'Canais com clássicos e programas retrô.',
    'séries': 'Canais dedicados a séries de TV de diversos gêneros.',
    'tv brasileira': 'Canais e conteúdos de produção brasileira.',
    'anime & geek': 'Canais de anime e cultura geek.',
    'mtv': 'Canais da marca MTV.',
    'nickelodeon': 'Canais da marca Nickelodeon.',
    'star trek': 'Canais dedicados ao universo Star Trek.',
    'south park br': 'Canais dedicados a South Park.',
}


def _descricao_categoria(nome):
    return DESCRICOES_CATEGORIA.get(nome.strip().lower(),
                                     'Canais da guia "{}" da Pluto TV.'.format(nome))


def build_url(params):
    return BASE_URL + '?' + urllib.parse.urlencode(params)


def _parse_m3u(text):
    """Retorna dict {categoria: [ {nome, tvg_id, logo, url} ]}"""
    categorias = {}
    linhas = text.splitlines()
    pendente = None
    for linha in linhas:
        linha = linha.strip()
        if not linha:
            continue
        if linha.startswith('#EXTINF'):
            m = EXTINF_RE.match(linha)
            if not m:
                pendente = None
                continue
            attrs = dict(ATTR_RE.findall(m.group('attrs')))
            nome = m.group('title').strip()
            pendente = {
                'nome': nome,
                'tvg_id': attrs.get('tvg-id', ''),
                'logo': attrs.get('tvg-logo', ''),
                'categoria': attrs.get('group-title', 'Outros').strip() or 'Outros',
            }
        elif linha.startswith('#'):
            continue
        else:
            if pendente is not None:
                pendente['url'] = linha
                categorias.setdefault(pendente['categoria'], []).append(pendente)
                pendente = None
    return categorias


def _carregar_cache():
    try:
        if xbmcvfs.exists(CACHE_FILE):
            f = xbmcvfs.File(CACHE_FILE)
            raw = f.read()
            f.close()
            dados = json.loads(raw)
            if time.time() - dados.get('timestamp', 0) < CACHE_TTL:
                return dados.get('categorias')
    except Exception as e:
        log('Falha ao ler cache: {}'.format(e))
    return None


def _salvar_cache(categorias):
    try:
        if not xbmcvfs.exists(PROFILE_DIR):
            xbmcvfs.mkdirs(PROFILE_DIR)
        f = xbmcvfs.File(CACHE_FILE, 'w')
        f.write(json.dumps({'timestamp': time.time(), 'categorias': categorias}))
        f.close()
    except Exception as e:
        log('Falha ao salvar cache: {}'.format(e))


_ULTIMO_ERRO = [None]


def obter_categorias(forcar=False):
    if not forcar:
        cache = _carregar_cache()
        if cache:
            return cache
    try:
        texto = _http_get(_playlist_url(), timeout=20)
        categorias = _parse_m3u(texto)
        if not categorias:
            _ULTIMO_ERRO[0] = 'A playlist respondeu, mas nenhum canal foi reconhecido (formato inesperado)'
        else:
            _salvar_cache(categorias)
        return categorias
    except Exception as e:
        _ULTIMO_ERRO[0] = '{}: {}'.format(type(e).__name__, e)
        log('Erro ao baixar playlist: {}'.format(_ULTIMO_ERRO[0]))
        cache = _carregar_cache()
        return cache or {}


def menu_principal():
    xbmcplugin.setPluginCategory(HANDLE, 'Pluto TV')
    xbmcplugin.setContent(HANDLE, 'videos')

    categorias = obter_categorias()
    if not categorias:
        detalhe = _ULTIMO_ERRO[0] or 'motivo desconhecido'
        item = xbmcgui.ListItem(label='Não foi possível carregar os canais: {} (toque para tentar de novo)'.format(detalhe))
        item.setArt({'icon': ICON, 'fanart': FANART})
        xbmcplugin.addDirectoryItem(HANDLE, build_url({'action': 'atualizar'}), item, False)
        xbmcplugin.endOfDirectory(HANDLE, succeeded=True)
        return

    for nome in sorted(categorias.keys(), key=lambda s: s.lower()):
        item = xbmcgui.ListItem(label=nome)
        item.setArt({'icon': ICON, 'fanart': FANART, 'thumb': ICON})
        item.setInfo('video', {'title': nome, 'plot': _descricao_categoria(nome), 'mediatype': 'video'})
        url = build_url({'action': 'categoria', 'nome': nome, 'pagina': 0})
        xbmcplugin.addDirectoryItem(HANDLE, url, item, True)

    item_att = xbmcgui.ListItem(label='[COLOR yellow]Atualizar lista de canais[/COLOR]')
    item_att.setArt({'icon': ICON, 'fanart': FANART})
    xbmcplugin.addDirectoryItem(HANDLE, build_url({'action': 'atualizar'}), item_att, False)

    xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_LABEL_IGNORE_THE)
    xbmcplugin.endOfDirectory(HANDLE, succeeded=True)


def listar_categoria(nome, pagina):
    xbmcplugin.setPluginCategory(HANDLE, nome)
    xbmcplugin.setContent(HANDLE, 'videos')

    categorias = obter_categorias()
    canais = categorias.get(nome, [])
    canais = sorted(canais, key=lambda c: c['nome'].lower())

    inicio = pagina * PAGE_SIZE
    fim = inicio + PAGE_SIZE
    pagina_atual = canais[inicio:fim]

    epg_por_id = _obter_epg_em_lote(pagina_atual)

    for canal in pagina_atual:
        item = xbmcgui.ListItem(label=canal['nome'])
        logo = canal.get('logo') or ICON
        item.setArt({'icon': logo, 'thumb': logo, 'fanart': FANART})
        plot = epg_por_id.get(canal.get('tvg_id')) or 'Programação não disponível para este canal.'
        item.setInfo('video', {'title': canal['nome'], 'plot': plot, 'mediatype': 'video'})
        item.setProperty('IsPlayable', 'true')
        url = build_url({'action': 'tocar', 'url': canal['url']})
        xbmcplugin.addDirectoryItem(HANDLE, url, item, False)

    if fim < len(canais):
        item_prox = xbmcgui.ListItem(label='[COLOR yellow]>> Próxima página[/COLOR]')
        item_prox.setArt({'icon': ICON, 'fanart': FANART})
        item_prox.setProperty('SpecialSort', 'bottom')
        url = build_url({'action': 'categoria', 'nome': nome, 'pagina': pagina + 1})
        xbmcplugin.addDirectoryItem(HANDLE, url, item_prox, True)

    if pagina > 0:
        item_ant = xbmcgui.ListItem(label='[COLOR yellow]<< Página anterior[/COLOR]')
        item_ant.setArt({'icon': ICON, 'fanart': FANART})
        item_ant.setProperty('SpecialSort', 'bottom')
        url = build_url({'action': 'categoria', 'nome': nome, 'pagina': pagina - 1})
        xbmcplugin.addDirectoryItem(HANDLE, url, item_ant, True)

    xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_UNSORTED)
    xbmcplugin.endOfDirectory(HANDLE, succeeded=True)


STREAM_USER_AGENT = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                     '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')


def tocar(url_canal):
    # Os links já vêm com um token de sessão (jwt) válido embutido pela
    # própria fonte da playlist; só reforçamos com um User-Agent de
    # navegador por segurança, igual fazíamos antes.
    headers = urllib.parse.urlencode({'User-Agent': STREAM_USER_AGENT})
    url_com_headers = '{}|{}'.format(url_canal, headers)
    item = xbmcgui.ListItem(path=url_com_headers)
    item.setProperty('IsPlayable', 'true')
    item.setMimeType('application/vnd.apple.mpegurl')
    item.setContentLookup(False)
    xbmcplugin.setResolvedUrl(HANDLE, True, item)


def _testar_link(url):
    try:
        headers = {'User-Agent': STREAM_USER_AGENT, 'Range': 'bytes=0-2048'}
        req = urllib.request.Request(url, headers=headers, method='GET')
        with urllib.request.urlopen(req, timeout=7) as resp:
            codigo = resp.getcode()
            return codigo < 400, codigo
    except urllib.error.HTTPError as e:
        return e.code < 400, e.code
    except Exception as e:
        return False, type(e).__name__


def _executar_verificacao(categorias, titulo_progresso='Pluto TV'):
    todos = []
    for cat, lista in categorias.items():
        for canal in lista:
            todos.append((cat, canal['nome'], canal['url']))

    if not todos:
        return None

    total = len(todos)
    progresso = xbmcgui.DialogProgress()
    progresso.create(titulo_progresso, 'Testando {} canais...'.format(total))

    quebrados = []
    concluidos = [0]

    def checar(item):
        cat, nome, url = item
        ok, info = _testar_link(url)
        return (cat, nome, ok, info)

    with ThreadPoolExecutor(max_workers=15) as executor:
        futuros = [executor.submit(checar, item) for item in todos]
        for futuro in futuros:
            if progresso.iscanceled():
                executor.shutdown(wait=False, cancel_futures=True)
                break
            cat, nome, ok, info = futuro.result()
            concluidos[0] += 1
            if not ok:
                quebrados.append('{} / {}  [{}]'.format(cat, nome, info))
            pct = int(concluidos[0] * 100 / total)
            progresso.update(pct, 'Testado {}/{} — {} com problema até agora'.format(
                concluidos[0], total, len(quebrados)))

    progresso.close()
    quebrados.sort()
    return quebrados, total


def atualizar():
    categorias = obter_categorias(forcar=True)
    if not categorias:
        detalhe = _ULTIMO_ERRO[0] or 'motivo desconhecido'
        xbmcgui.Dialog().notification('Pluto TV', 'Falha: {}'.format(detalhe), xbmcgui.NOTIFICATION_ERROR, 6000)
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
        return

    resultado = _executar_verificacao(categorias, titulo_progresso='Atualizando Pluto TV')
    if resultado is None:
        xbmcgui.Dialog().notification('Pluto TV', 'Lista de canais atualizada', xbmcgui.NOTIFICATION_INFO, 3000)
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
        return

    quebrados, total = resultado
    if quebrados:
        texto = '\n'.join(quebrados)
        xbmcgui.Dialog().textviewer(
            'Atualizado — {} de {} canais com link quebrado'.format(len(quebrados), total), texto)
    else:
        xbmcgui.Dialog().notification(
            'Pluto TV', 'Atualizado: {} canais, todos funcionando'.format(total),
            xbmcgui.NOTIFICATION_INFO, 4000)
    xbmcplugin.endOfDirectory(HANDLE, succeeded=False)


def router():
    params = dict(parse_qsl(sys.argv[2][1:]))
    action = params.get('action')

    if not action:
        menu_principal()
    elif action == 'categoria':
        listar_categoria(params.get('nome', ''), int(params.get('pagina', 0)))
    elif action == 'tocar':
        tocar(params.get('url'))
    elif action == 'atualizar':
        atualizar()
    else:
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)


if __name__ == '__main__':
    router()
