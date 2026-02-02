import feedparser
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from collections import defaultdict
import urllib.request
import re
import config
import sys
import io

# Configurar UTF-8 para stdout (compatibilidad Windows/Linux)
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# REGISTRAR NAMESPACES PRIMERO (CRUCIAL)
ET.register_namespace('itunes', 'http://www.itunes.com/dtds/podcast-1.0.dtd')
ET.register_namespace('content', 'http://purl.org/rss/1.0/modules/content/')
ET.register_namespace('atom', 'http://www.w3.org/2005/Atom')

def parse_date(date_string):
    """Convierte string de fecha RSS a datetime (sin timezone)"""
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(date_string)
        return dt.replace(tzinfo=None)
    except:
        try:
            return datetime.strptime(date_string, "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=None)
        except:
            return datetime.now().replace(tzinfo=None)

def format_date(dt):
    """Formatea datetime a RFC-2822"""
    if dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
    return dt.strftime("%a, %d %b %Y %H:%M:%S GMT")

def clean_episode_title(title):
    """Elimina el prefijo 'Pasajes de la Historia: ' del título"""
    prefix = "Pasajes de la Historia: "
    if title.startswith(prefix):
        return title[len(prefix):]
    return title

def extract_durations_simple(xml_content):
    """Extrae duraciones usando regex con múltiples métodos de matching"""
    durations_map = {}

    # Dividir en items
    items = re.findall(r'<item>.*?</item>', xml_content, re.DOTALL)

    for idx, item in enumerate(items):
        # Extraer GUID
        guid_match = re.search(r'<guid[^>]*>([^<]+)</guid>', item)
        # Extraer duración
        duration_match = re.search(r'<itunes:duration>([^<]+)</itunes:duration>', item)

        if guid_match and duration_match:
            guid = guid_match.group(1).strip()
            duration = duration_match.group(1).strip()
            durations_map[guid] = duration
        else:
            # Debug: mostrar items sin duración
            title_match = re.search(r'<title>([^<]+)</title>', item)
            title = title_match.group(1) if title_match else "SIN TÍTULO"
            if not duration_match:
                print(f"  ⚠ Item {idx} sin duración: {title[:60]}")

    print(f"  ✓ Duraciones extraídas: {len(durations_map)} items")
    return durations_map

def get_durations_from_xml(feed_url):
    """Descarga el XML y extrae las duraciones"""
    try:
        request = urllib.request.Request(
            feed_url,
            headers={'User-Agent': 'Mozilla/5.0'}
        )
        
        with urllib.request.urlopen(request, timeout=30) as response:
            xml_content = response.read().decode('utf-8')
        
        durations_map = extract_durations_simple(xml_content)
        print(f"Duraciones extraídas del feed original: {len(durations_map)}")
        
        return durations_map
        
    except Exception as e:
        print(f"ERROR extrayendo duraciones: {e}")
        return {}

def modify_duplicate_dates(feed_url, durations_map):
    """Descarga RSS y modifica fechas duplicadas"""
    
    feed = feedparser.parse(feed_url)
    
    if not feed.entries:
        print("ERROR: No se encontraron episodios")
        return feed, []
    
    # Agrupar episodios por fecha
    date_groups = defaultdict(list)
    
    for entry in feed.entries:
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            date_obj = datetime(*entry.published_parsed[:6])
        elif 'published' in entry:
            date_obj = parse_date(entry.published)
        else:
            date_obj = datetime.now()
        
        date_obj = date_obj.replace(tzinfo=None)
        date_key = date_obj.date()

        date_groups[date_key].append({
            'entry': entry,
            'original_date': date_obj
        })
    
    # Asignar duraciones a episodios
    matched_count = 0
    for date_key, episodes in date_groups.items():
        for episode_data in episodes:
            entry = episode_data['entry']

            # Método 1: Usar el ID (GUID) de feedparser
            guid = entry.get('id', '')
            if guid and guid in durations_map:
                entry['duration_from_xml'] = durations_map[guid]
                matched_count += 1
                continue

            # Método 2: Usar el link como fallback
            link = entry.get('link', '')
            if link and link in durations_map:
                entry['duration_from_xml'] = durations_map[link]
                matched_count += 1
                continue

            # Método 3: Intentar extraer GUID del link
            # Algunos feeds usan la URL como GUID
            for guid_key in durations_map.keys():
                if guid_key in link or link in guid_key:
                    entry['duration_from_xml'] = durations_map[guid_key]
                    matched_count += 1
                    break

    print(f"Episodios con duración mapeada: {matched_count}/{len(feed.entries)}")

    # Modificar fechas duplicadas
    modified_entries = []

    for date_key, episodes in sorted(date_groups.items(), reverse=True):
        if len(episodes) > 1:
            episodes.sort(key=lambda x: x['original_date'])

            for idx, episode_data in enumerate(episodes):
                new_date = datetime.combine(date_key, datetime.min.time()) - timedelta(days=idx)
                episode_data['modified_date'] = new_date
                modified_entries.append(episode_data)
        else:
            episode_data = episodes[0]
            episode_data['modified_date'] = episode_data['original_date']
            modified_entries.append(episode_data)
    
    modified_entries.sort(key=lambda x: x['modified_date'], reverse=True)
    
    return feed, modified_entries

def create_rss_xml(original_feed, modified_entries):
    """Crea archivo XML RSS con las fechas modificadas"""
    
    # Crear RSS root
    rss = ET.Element('rss')
    rss.set('version', '2.0')
    rss.set('xmlns:itunes', 'http://www.itunes.com/dtds/podcast-1.0.dtd')
    rss.set('xmlns:content', 'http://purl.org/rss/1.0/modules/content/')
    
    channel = ET.SubElement(rss, 'channel')
    
    # Metadatos básicos del canal
    ET.SubElement(channel, 'title').text = config.FEED_TITLE
    ET.SubElement(channel, 'description').text = config.FEED_DESCRIPTION
    ET.SubElement(channel, 'link').text = config.FEED_LINK

    # Atom self link (requerido por PSP-1)
    atom_link = ET.SubElement(channel, '{http://www.w3.org/2005/Atom}link')
    atom_link.set('rel', 'self')
    atom_link.set('href', config.FEED_LINK)
    atom_link.set('type', 'application/rss+xml')

    # iTunes summary (requerido por Apple)
    ET.SubElement(channel, 'itunes:summary').text = config.FEED_SUMMARY
    
    # Copiar metadatos del feed original
    original_channel = original_feed.feed
    
    # Idioma
    if hasattr(original_channel, 'language'):
        lang = original_channel.language
        if lang.startswith('es'):
            lang = 'es'
        ET.SubElement(channel, 'language').text = lang
    else:
        ET.SubElement(channel, 'language').text = 'es'
    
    # Copyright
    if hasattr(original_channel, 'rights'):
        ET.SubElement(channel, 'copyright').text = original_channel.rights
    
    # Autor iTunes
    if hasattr(original_channel, 'author'):
        itunes_author = ET.SubElement(channel, 'itunes:author')
        itunes_author.text = original_channel.author
    elif hasattr(original_channel, 'itunes_author'):
        itunes_author = ET.SubElement(channel, 'itunes:author')
        itunes_author.text = original_channel.itunes_author
    else:
        # Usar configuración por defecto
        ET.SubElement(channel, 'itunes:author').text = config.FEED_AUTHOR

    # Categorías iTunes (REQUERIDO por Apple)
    for category in config.ITUNES_CATEGORIES:
        cat_elem = ET.SubElement(channel, 'itunes:category')
        cat_elem.set('text', category[0])
        if len(category) > 1:
            subcat_elem = ET.SubElement(cat_elem, 'itunes:category')
            subcat_elem.set('text', category[1])
    
    # Imagen del podcast
    podcast_image_url = None
    
    if hasattr(original_channel, 'image') and isinstance(original_channel.image, dict):
        podcast_image_url = original_channel.image.get('href', original_channel.image.get('url', ''))
    elif hasattr(original_channel, 'itunes_image'):
        if isinstance(original_channel.itunes_image, dict):
            podcast_image_url = original_channel.itunes_image.get('href', '')
        else:
            podcast_image_url = str(original_channel.itunes_image)
    
    # Si encontramos imagen, añadirla
    if podcast_image_url:
        image_elem = ET.SubElement(channel, 'image')
        ET.SubElement(image_elem, 'url').text = podcast_image_url
        ET.SubElement(image_elem, 'title').text = config.FEED_TITLE
        ET.SubElement(image_elem, 'link').text = config.FEED_LINK
        
        itunes_image = ET.SubElement(channel, 'itunes:image')
        itunes_image.set('href', podcast_image_url)
    
    # Explicit (usar configuración por defecto)
    ET.SubElement(channel, 'itunes:explicit').text = config.FEED_EXPLICIT
    
    # Añadir episodios
    episodes_with_duration = 0
    
    for episode_data in modified_entries:
        entry = episode_data['entry']
        modified_date = episode_data['modified_date']
        
        item = ET.SubElement(channel, 'item')
        
        # Título (limpio, sin prefijo)
        original_title = entry.get('title', 'Sin título')
        clean_title = clean_episode_title(original_title)
        ET.SubElement(item, 'title').text = clean_title
        
        # Descripción
        description = entry.get('summary', entry.get('description', ''))
        ET.SubElement(item, 'description').text = description
        
        # Fecha modificada
        ET.SubElement(item, 'pubDate').text = format_date(modified_date)
        
        # GUID
        guid_text = entry.get('id', entry.get('link', str(modified_date)))
        guid_elem = ET.SubElement(item, 'guid')
        guid_elem.set('isPermaLink', 'false')
        guid_elem.text = guid_text
        
        # Enlace
        if 'link' in entry:
            ET.SubElement(item, 'link').text = entry.link
        
        # Audio enclosure
        enclosure_found = False
        
        if hasattr(entry, 'enclosures') and len(entry.enclosures) > 0:
            enc = entry.enclosures[0]
            url = enc.get('href', enc.get('url', ''))
            if url:
                enclosure = ET.SubElement(item, 'enclosure')
                enclosure.set('url', url)
                enclosure.set('type', enc.get('type', 'audio/mpeg'))
                enclosure.set('length', str(enc.get('length', '0')))
                enclosure_found = True
        
        if not enclosure_found and hasattr(entry, 'links'):
            for link in entry.links:
                if link.get('type', '').startswith('audio'):
                    enclosure = ET.SubElement(item, 'enclosure')
                    enclosure.set('url', link.get('href', ''))
                    enclosure.set('type', link.get('type', 'audio/mpeg'))
                    enclosure.set('length', str(link.get('length', '0')))
                    break
        
        # Duración iTunes - USAR PREFIJO CORRECTO
        duration = entry.get('duration_from_xml')
        if duration:
            itunes_duration = ET.SubElement(item, 'itunes:duration')
            itunes_duration.text = duration
            episodes_with_duration += 1
        
        # Imagen del episodio
        if hasattr(entry, 'image') and isinstance(entry.image, dict) and 'href' in entry.image:
            itunes_ep_image = ET.SubElement(item, 'itunes:image')
            itunes_ep_image.set('href', entry.image.href)
    
    print(f"Episodios con duración: {episodes_with_duration}/{len(modified_entries)}")
    
    return rss

def main():
    print("=== Modificando RSS de Pasajes de la Historia ===\n")

    print("Paso 1: Extrayendo duraciones del XML original...")
    durations_map = get_durations_from_xml(config.ORIGINAL_FEED_URL)

    if not durations_map:
        print("⚠ ADVERTENCIA: No se pudieron extraer duraciones del feed original")

    print("\nPaso 2: Modificando fechas duplicadas y mapeando duraciones...")
    original_feed, modified_entries = modify_duplicate_dates(config.ORIGINAL_FEED_URL, durations_map)

    if not modified_entries:
        print("ERROR: No se pudieron procesar episodios")
        exit(1)

    print(f"Total de episodios procesados: {len(modified_entries)}")

    print("\nPaso 3: Creando XML RSS...")
    rss_xml = create_rss_xml(original_feed, modified_entries)

    # Guardar archivo
    tree = ET.ElementTree(rss_xml)
    # ET.indent() solo disponible en Python 3.9+
    if hasattr(ET, 'indent'):
        ET.indent(tree, space='  ')
    tree.write('feed.xml', encoding='utf-8', xml_declaration=True)

    # Verificar que se escribieron las duraciones
    with open('feed.xml', 'r', encoding='utf-8') as f:
        feed_content = f.read()
        duration_count = feed_content.count('<itunes:duration>')
        print(f"\n✓ Feed generado: {config.FEED_LINK}")
        print(f"✓ Duraciones en el feed: {duration_count} episodios")

        if duration_count == 0:
            print("⚠ ADVERTENCIA: No se encontraron duraciones en el feed generado")
            print("   Revisa el XML de salida para verificar")
        elif duration_count < len(modified_entries):
            print(f"⚠ ADVERTENCIA: Solo {duration_count}/{len(modified_entries)} episodios tienen duración")
        else:
            print(f"✓ Todos los episodios tienen duración correctamente asignada")

if __name__ == "__main__":
    main()
