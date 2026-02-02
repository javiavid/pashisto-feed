import feedparser
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import config

def parse_date(date_string):
    """Convierte string de fecha RSS a datetime (sin timezone)"""
    try:
        # Intentar parsear con feedparser que maneja múltiples formatos
        import time
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(date_string)
        # Convertir a naive datetime (sin timezone) para evitar conflictos
        return dt.replace(tzinfo=None)
    except:
        try:
            return datetime.strptime(date_string, "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=None)
        except:
            return datetime.now().replace(tzinfo=None)

def format_date(dt):
    """Formatea datetime a RFC-2822"""
    # Asegurar que sea naive datetime
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
        # Usar published_parsed si está disponible
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            date_obj = datetime(*entry.published_parsed[:6])
        elif 'published' in entry:
            date_obj = parse_date(entry.published)
        else:
            date_obj = datetime.now()
        
        # Asegurar que sea naive datetime
        date_obj = date_obj.replace(tzinfo=None)
        
        date_key = date_obj.date()  # Solo la fecha, sin hora
        date_groups[date_key].append({
            'entry': entry,
            'original_date': date_obj
        })
    
    # Modificar fechas duplicadas
    modified_entries = []
    
    for date_key, episodes in sorted(date_groups.items(), reverse=True):
        if len(episodes) > 1:
            print(f"Encontrados {len(episodes)} episodios en {date_key}")
            # Ordenar por hora original
            episodes.sort(key=lambda x: x['original_date'])
            
            for idx, episode_data in enumerate(episodes):
                # Añadir días a los episodios duplicados (hacia atrás)
                new_date = datetime.combine(date_key, datetime.min.time()) - timedelta(days=idx)
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
        
        # Descripción
        description = entry.get('summary', entry.get('description', ''))
        ET.SubElement(item, 'description').text = description
        
        # Fecha modificada
        ET.SubElement(item, 'pubDate').text = format_date(modified_date)
        
        # GUID
        guid_text = entry.get('id', entry.get('link', str(modified_date)))
        ET.SubElement(item, 'guid', isPermaLink='false').text = guid_text
        
        # Enlace al episodio
        if 'link' in entry:
            ET.SubElement(item, 'link').text = entry.link
        
        # Audio enclosure (lo más importante para podcasts)
        enclosure_found = False
        
        # Buscar enclosure en múltiples ubicaciones
        if hasattr(entry, 'enclosures') and len(entry.enclosures) > 0:
            enc = entry.enclosures[0]
            url = enc.get('href', enc.get('url', ''))
            if url:
                ET.SubElement(item, 'enclosure', {
                    'url': url,
                    'type': enc.get('type', 'audio/mpeg'),
                    'length': str(enc.get('length', '0'))
                })
                enclosure_found = True
        
        # Si no se encontró, buscar en links
        if not enclosure_found and hasattr(entry, 'links'):
            for link in entry.links:
                if link.get('type', '').startswith('audio'):
                    ET.SubElement(item, 'enclosure', {
                        'url': link.get('href', ''),
                        'type': link.get('type', 'audio/mpeg'),
                        'length': str(link.get('length', '0'))
                    })
                    break
        
        # Duración iTunes si existe
        if hasattr(entry, 'itunes_duration'):
            ET.SubElement(item, '{http://www.itunes.com/dtds/podcast-1.0.dtd}duration').text = entry.itunes_duration
        
        # Imagen del episodio si existe
        if hasattr(entry, 'image') and 'href' in entry.image:
            ET.SubElement(item, '{http://www.itunes.com/dtds/podcast-1.0.dtd}image', 
                         href=entry.image.href)
    
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
    ET.indent(tree, space='  ')  # Pretty print
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
