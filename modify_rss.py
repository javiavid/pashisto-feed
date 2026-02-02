import feedparser
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from collections import defaultdict
import config

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

def modify_duplicate_dates(feed_url):
    """Descarga RSS y modifica fechas duplicadas"""
    
    print(f"Descargando feed desde: {feed_url}")
    feed = feedparser.parse(feed_url)
    
    if not feed.entries:
        print("ERROR: No se encontraron episodios en el feed")
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
    
    # Modificar fechas duplicadas
    modified_entries = []
    
    for date_key, episodes in sorted(date_groups.items(), reverse=True):
        if len(episodes) > 1:
            print(f"Encontrados {len(episodes)} episodios en {date_key}")
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
    
    # Crear RSS root - SIN duplicar namespaces
    rss = ET.Element('rss')
    rss.set('version', '2.0')
    rss.set('xmlns:itunes', 'http://www.itunes.com/dtds/podcast-1.0.dtd')
    rss.set('xmlns:content', 'http://purl.org/rss/1.0/modules/content/')
    
    channel = ET.SubElement(rss, 'channel')
    
    # Metadatos básicos del canal
    ET.SubElement(channel, 'title').text = config.FEED_TITLE
    ET.SubElement(channel, 'description').text = config.FEED_DESCRIPTION
    ET.SubElement(channel, 'link').text = config.FEED_LINK
    
    # Copiar metadatos del feed original
    original_channel = original_feed.feed
    
    # Idioma (formato correcto es 'es' no 'es-es')
    if hasattr(original_channel, 'language'):
        lang = original_channel.language
        # Normalizar a formato de 2 letras si es necesario
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
        itunes_author = ET.SubElement(channel, '{http://www.itunes.com/dtds/podcast-1.0.dtd}author')
        itunes_author.text = original_channel.author
    elif hasattr(original_channel, 'itunes_author'):
        itunes_author = ET.SubElement(channel, '{http://www.itunes.com/dtds/podcast-1.0.dtd}author')
        itunes_author.text = original_channel.itunes_author
    
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
        # Imagen RSS estándar
        image_elem = ET.SubElement(channel, 'image')
        ET.SubElement(image_elem, 'url').text = podcast_image_url
        ET.SubElement(image_elem, 'title').text = config.FEED_TITLE
        ET.SubElement(image_elem, 'link').text = config.FEED_LINK
        
        # Imagen iTunes
        itunes_image = ET.SubElement(channel, '{http://www.itunes.com/dtds/podcast-1.0.dtd}image')
        itunes_image.set('href', podcast_image_url)
    
    # Explicit
    itunes_explicit = ET.SubElement(channel, '{http://www.itunes.com/dtds/podcast-1.0.dtd}explicit')
    if hasattr(original_channel, 'itunes_explicit'):
        itunes_explicit.text = original_channel.itunes_explicit
    else:
        itunes_explicit.text = 'no'
    
    # Añadir episodios
    for episode_data in modified_entries:
        entry = episode_data['entry']
        modified_date = episode_data['modified_date']
        
        item = ET.SubElement(channel, 'item')
        
        # Título
        ET.SubElement(item, 'title').text = entry.get('title', 'Sin título')
        
        # Descripción
        description = entry.get('summary', entry.get('description', ''))
        ET.SubElement(item, 'description').text = description
        
        # Fecha modificada (RFC-2822 format)
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
        
        # Duración iTunes
        if hasattr(entry, 'itunes_duration'):
            itunes_duration = ET.SubElement(item, '{http://www.itunes.com/dtds/podcast-1.0.dtd}duration')
            itunes_duration.text = str(entry.itunes_duration)
        
        # Imagen del episodio
        if hasattr(entry, 'image') and isinstance(entry.image, dict) and 'href' in entry.image:
            itunes_ep_image = ET.SubElement(item, '{http://www.itunes.com/dtds/podcast-1.0.dtd}image')
            itunes_ep_image.set('href', entry.image.href)
    
    return rss

def main():
    print("=== Iniciando modificación de RSS ===")
    
    # Modificar fechas
    original_feed, modified_entries = modify_duplicate_dates(config.ORIGINAL_FEED_URL)
    
    if not modified_entries:
        print("ERROR: No se pudieron procesar episodios")
        exit(1)
    
    print(f"\nTotal de episodios procesados: {len(modified_entries)}")
    
    # Crear XML
    rss_xml = create_rss_xml(original_feed, modified_entries)
    
    # Guardar archivo
    tree = ET.ElementTree(rss_xml)
    ET.indent(tree, space='  ')
    tree.write('feed.xml', encoding='utf-8', xml_declaration=True)
    
    print("\n✓ Archivo feed.xml generado correctamente")
    print(f"✓ URL del feed: {config.FEED_LINK}")
    
    # Mostrar algunos ejemplos
    print("\n--- Primeros 5 episodios ---")
    for i, ep in enumerate(modified_entries[:5]):
        print(f"{i+1}. {ep['entry'].get('title', 'Sin título')}")
        print(f"   Fecha: {ep['modified_date'].strftime('%Y-%m-%d')}")

if __name__ == "__main__":
    main()
