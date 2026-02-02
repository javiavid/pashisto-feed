import feedparser
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from collections import defaultdict
import urllib.request
import config

def parse_date(date_string):
    """Convierte string de fecha RSS a datetime"""
    try:
        return datetime.strptime(date_string, "%a, %d %b %Y %H:%M:%S %Z")
    except:
        try:
            return datetime.strptime(date_string, "%a, %d %b %Y %H:%M:%S %z")
        except:
            return datetime.now()

def format_date(dt):
    """Formatea datetime a RFC-2822"""
    return dt.strftime("%a, %d %b %Y %H:%M:%S GMT")

def modify_duplicate_dates(feed_url):
    """Descarga RSS y modifica fechas duplicadas"""
    
    print(f"Descargando feed desde: {feed_url}")
    feed = feedparser.parse(feed_url)
    
    # Agrupar episodios por fecha
    date_groups = defaultdict(list)
    
    for entry in feed.entries:
        pub_date = entry.get('published', '')
        if pub_date:
            date_obj = parse_date(pub_date)
            date_key = date_obj.date()  # Solo la fecha, sin hora
            date_groups[date_key].append({
                'entry': entry,
                'original_date': date_obj
            })
    
    # Modificar fechas duplicadas
    modified_entries = []
    
    for date_key, episodes in date_groups.items():
        if len(episodes) > 1:
            print(f"Encontrados {len(episodes)} episodios en {date_key}")
            # Ordenar por hora original
            episodes.sort(key=lambda x: x['original_date'])
            
            for idx, episode_data in enumerate(episodes):
                # Añadir días a los episodios duplicados
                new_date = datetime.combine(date_key, datetime.min.time()) + timedelta(days=idx)
                episode_data['modified_date'] = new_date
                modified_entries.append(episode_data)
        else:
            # No hay duplicados, mantener fecha original
            episode_data = episodes[0]
            episode_data['modified_date'] = episode_data['original_date']
            modified_entries.append(episode_data)
    
    # Ordenar por fecha modificada (más reciente primero)
    modified_entries.sort(key=lambda x: x['modified_date'], reverse=True)
    
    return feed, modified_entries

def create_rss_xml(original_feed, modified_entries):
    """Crea archivo XML RSS con las fechas modificadas"""
    
    # Crear estructura RSS 2.0
    rss = ET.Element('rss', version='2.0', attrib={
        'xmlns:itunes': 'http://www.itunes.com/dtds/podcast-1.0.dtd',
        'xmlns:content': 'http://purl.org/rss/1.0/modules/content/'
    })
    
    channel = ET.SubElement(rss, 'channel')
    
    # Metadatos del canal
    ET.SubElement(channel, 'title').text = config.FEED_TITLE
    ET.SubElement(channel, 'description').text = config.FEED_DESCRIPTION
    ET.SubElement(channel, 'link').text = config.FEED_LINK
    
    # Copiar metadatos adicionales del feed original si existen
    if hasattr(original_feed.feed, 'language'):
        ET.SubElement(channel, 'language').text = original_feed.feed.language
    
    if hasattr(original_feed.feed, 'image'):
        image = ET.SubElement(channel, 'image')
        ET.SubElement(image, 'url').text = original_feed.feed.image.get('href', '')
        ET.SubElement(image, 'title').text = config.FEED_TITLE
        ET.SubElement(image, 'link').text = config.FEED_LINK
    
    # Añadir episodios con fechas modificadas
    for episode_data in modified_entries:
        entry = episode_data['entry']
        modified_date = episode_data['modified_date']
        
        item = ET.SubElement(channel, 'item')
        
        ET.SubElement(item, 'title').text = entry.get('title', 'Sin título')
        ET.SubElement(item, 'description').text = entry.get('summary', '')
        ET.SubElement(item, 'pubDate').text = format_date(modified_date)
        ET.SubElement(item, 'guid').text = entry.get('id', entry.get('link', ''))
        
        # Enlace al episodio
        if 'link' in entry:
            ET.SubElement(item, 'link').text = entry.link
        
        # Audio enclosure (lo más importante para podcasts)
        if 'enclosures' in entry and len(entry.enclosures) > 0:
            enclosure = entry.enclosures[0]
            ET.SubElement(item, 'enclosure', {
                'url': enclosure.get('href', enclosure.get('url', '')),
                'type': enclosure.get('type', 'audio/mpeg'),
                'length': str(enclosure.get('length', '0'))
            })
        
        # Duración iTunes si existe
        if 'itunes_duration' in entry:
            ET.SubElement(item, '{http://www.itunes.com/dtds/podcast-1.0.dtd}duration').text = entry.itunes_duration
    
    return rss

def main():
    print("=== Iniciando modificación de RSS ===")
    
    # Modificar fechas
    original_feed, modified_entries = modify_duplicate_dates(config.ORIGINAL_FEED_URL)
    
    print(f"\nTotal de episodios procesados: {len(modified_entries)}")
    
    # Crear XML
    rss_xml = create_rss_xml(original_feed, modified_entries)
    
    # Guardar archivo
    tree = ET.ElementTree(rss_xml)
    ET.indent(tree, space='  ')  # Pretty print
    tree.write('feed.xml', encoding='utf-8', xml_declaration=True)
    
    print("\n✓ Archivo feed.xml generado correctamente")
    print(f"✓ URL del feed: {config.FEED_LINK}")

if __name__ == "__main__":
    main()
