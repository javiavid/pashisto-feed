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
    """Crea archivo XML RSS con las fechas modificadas y metadatos completos"""
    
    # Registrar namespace iTunes
    ET.register_namespace('itunes', 'http://www.itunes.com/dtds/podcast-1.0.dtd')
    ET.register_namespace('content', 'http://purl.org/rss/1.0/modules/content/')
    
    # Crear estructura RSS 2.0
    rss = ET.Element('rss', version='2.0', attrib={
        'xmlns:itunes': 'http://www.itunes.com/dtds/podcast-1.0.dtd',
        'xmlns:content': 'http://purl.org/rss/1.0/modules/content/'
    })
    
    channel = ET.SubElement(rss, 'channel')
    
    # Metadatos básicos del canal
    ET.SubElement(channel, 'title').text = config.FEED_TITLE
    ET.SubElement(channel, 'description').text = config.FEED_DESCRIPTION
    ET.SubElement(channel, 'link').text = config.FEED_LINK
    
    # Copiar metadatos del feed original
    original_channel = original_feed.feed
    
    # Idioma
    if hasattr(original_channel, 'language'):
        ET.SubElement(channel, 'language').text = original_channel.language
    else:
        ET.SubElement(channel, 'language').text = 'es'
    
    # Copyright
    if hasattr(original_channel, 'rights'):
        ET.SubElement(channel, 'copyright').text = original_channel.rights
    
    # Autor iTunes
    if hasattr(original_channel, 'author'):
        ET.SubElement(channel, '{http://www.itunes.com/dtds/podcast-1.0.dtd}author').text = original_channel.author
    elif hasattr(original_channel, 'itunes_author'):
        ET.SubElement(channel, '{http://www.itunes.com/dtds/podcast-1.0.dtd}author').text = original_channel.itunes_author
    
    # Imagen del podcast (CRÍTICO para Yoto)
    # Intentar obtener de múltiples fuentes
    podcast_image_url = None
    
    if hasattr(original_channel, 'image') and 'href' in original_channel.image:
        podcast_image_url = original_channel.image.href
    elif hasattr(original_channel, 'image') and 'url' in original_channel.image:
        podcast_image_url = original_channel.image.url
    elif hasattr(original_channel, 'itunes_image'):
        if isinstance(original_channel.itunes_image, dict):
            podcast_image_url = original_channel.itunes_image.get('href', '')
        else:
            podcast_image_url = original_channel.itunes_image
    
    # Añadir imagen estándar RSS
    if podcast_image_url:
        image = ET.SubElement(channel, 'image')
        ET.SubElement(image, 'url').text = podcast_image_url
        ET.SubElement(image, 'title').text = config.FEED_TITLE
        ET.SubElement(image, 'link').text = config.FEED_LINK
        
        # Añadir imagen iTunes (formato preferido por Yoto)
        ET.SubElement(channel, '{http://www.itunes.com/dtds/podcast-1.0.dtd}image', 
                     href=podcast_image_url)
    
    # Categoría iTunes
    if hasattr(original_channel, 'itunes_category'):
        category = ET.SubElement(channel, '{http://www.itunes.com/dtds/podcast-1.0.dtd}category',
                                text=original_channel.itunes_category)
    
    # Explicit
    if hasattr(original_channel, 'itunes_explicit'):
        ET.SubElement(channel, '{http://www.itunes.com/dtds/podcast-1.0.dtd}explicit').text = original_channel.itunes_explicit
    else:
        ET.SubElement(channel, '{http://www.itunes.com/dtds/podcast-1.0.dtd}explicit').text = 'no'
    
    # Owner
    if hasattr(original_channel, 'itunes_owner_name') or hasattr(original_channel, 'itunes_owner_email'):
        owner = ET.SubElement(channel, '{http://www.itunes.com/dtds/podcast-1.0.dtd}owner')
        if hasattr(original_channel, 'itunes_owner_name'):
            ET.SubElement(owner, '{http://www.itunes.com/dtds/podcast-1.0.dtd}name').text = original_channel.itunes_owner_name
        if hasattr(original_channel, 'itunes_owner_email'):
            ET.SubElement(owner, '{http://www.itunes.com/dtds/podcast-1.0.dtd}email').text = original_channel.itunes_owner_email
    
    # Añadir episodios con fechas modificadas
    for episode_data in modified_entries:
        entry = episode_data['entry']
        modified_date = episode_data['modified_date']
        
        item = ET.SubElement(channel, 'item')
        
        # Título
        ET.SubElement(item, 'title').text = entry.get('title', 'Sin título')
        
        # Descripción
        description = entry.get('summary', entry.get('description', ''))
        ET.SubElement(item, 'description').text = description
        
        # Fecha modificada (CRÍTICO para Yoto)
        ET.SubElement(item, 'pubDate').text = format_date(modified_date)
        
        # GUID
        guid_text = entry.get('id', entry.get('link', str(modified_date)))
        ET.SubElement(item, 'guid', isPermaLink='false').text = guid_text
        
        # Enlace
        if 'link' in entry:
            ET.SubElement(item, 'link').text = entry.link
        
        # Audio enclosure (CRÍTICO)
        enclosure_found = False
        
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
        
        if not enclosure_found and hasattr(entry, 'links'):
            for link in entry.links:
                if link.get('type', '').startswith('audio'):
                    ET.SubElement(item, 'enclosure', {
                        'url': link.get('href', ''),
                        'type': link.get('type', 'audio/mpeg'),
                        'length': str(link.get('length', '0'))
                    })
                    break
        
        # Duración iTunes
        if hasattr(entry, 'itunes_duration'):
            ET.SubElement(item, '{http://www.itunes.com/dtds/podcast-1.0.dtd}duration').text = str(entry.itunes_duration)
        
        # Autor iTunes
        if hasattr(entry, 'author'):
            ET.SubElement(item, '{http://www.itunes.com/dtds/podcast-1.0.dtd}author').text = entry.author
        elif hasattr(entry, 'itunes_author'):
            ET.SubElement(item, '{http://www.itunes.com/dtds/podcast-1.0.dtd}author').text = entry.itunes_author
        
        # Subtítulo iTunes
        if hasattr(entry, 'itunes_subtitle'):
            ET.SubElement(item, '{http://www.itunes.com/dtds/podcast-1.0.dtd}subtitle').text = entry.itunes_subtitle
        
        # Summary iTunes
        if hasattr(entry, 'itunes_summary'):
            ET.SubElement(item, '{http://www.itunes.com/dtds/podcast-1.0.dtd}summary').text = entry.itunes_summary
        
        # Imagen del episodio (opcional pero útil)
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
