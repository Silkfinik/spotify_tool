import os
import csv
import json
from urllib.parse import urlparse, unquote


def _find_header_mappings(headers: list[str]) -> dict:
    """
    Находит соответствие между стандартными именами полей и реальными заголовками в файле.
    """
    headers_lower = [h.lower() for h in headers]

    ALIASES = {
        'id': ['track_id', 'id', 'trackid'],
        'uri': ['uri', 'track_uri'],
        'name': ['track_name', 'name', 'title', 'название'],
        'artist': ['artist_name', 'artist', 'исполнитель', 'артист']
    }

    mappings = {}
    for canonical_name, alias_list in ALIASES.items():
        for alias in alias_list:
            if alias in headers_lower:
                original_header_index = headers_lower.index(alias)
                mappings[canonical_name] = headers[original_header_index]
                break
    return mappings


def parse_file(filepath: str) -> list[str]:
    """Определяет тип файла и вызывает соответствующий парсер."""
    _, extension = os.path.splitext(filepath)
    extension = extension.lower()

    if extension == '.csv':
        return parse_csv(filepath)
    elif extension == '.json':
        return parse_json(filepath)
    else:
        raise ValueError(f"Неподдерживаемый формат файла: {extension}")


def parse_csv(filepath: str) -> list[str]:
    """Читает CSV и извлекает данные для поиска треков, используя гибкое сопоставление колонок."""
    queries = []
    try:
        with open(filepath, mode='r', encoding='utf-8-sig') as csvfile:
            reader = csv.DictReader(csvfile)
            if not reader.fieldnames:
                return []

            mappings = _find_header_mappings(reader.fieldnames)

            for row in reader:
                if 'uri' in mappings and row.get(mappings['uri']):
                    track_id = os.path.basename(
                        unquote(urlparse(row[mappings['uri']]).path))
                    queries.append(track_id)
                elif 'id' in mappings and row.get(mappings['id']):
                    queries.append(row[mappings['id']])
                elif 'name' in mappings and 'artist' in mappings and row.get(mappings['name']) and row.get(mappings['artist']):
                    query = f"{row[mappings['artist']]} - {row[mappings['name']]}"
                    queries.append(query)
    except Exception as e:
        print(f"Ошибка чтения CSV: {e}")
        raise
    return queries


def parse_json(filepath: str) -> list[str]:
    """Читает JSON и извлекает данные для поиска, используя гибкое сопоставление колонок."""
    queries = []
    try:
        with open(filepath, mode='r', encoding='utf-8') as jsonfile:
            data = json.load(jsonfile)
            if not isinstance(data, list) or not data:
                raise TypeError(
                    "JSON должен содержать непустой список объектов")

            first_item = data[0]
            if not isinstance(first_item, dict):
                return []

            mappings = _find_header_mappings(list(first_item.keys()))

            for track in data:
                if not isinstance(track, dict):
                    continue
                # Логика приоритетов, аналогичная CSV
                if 'uri' in mappings and track.get(mappings['uri']):
                    track_id = os.path.basename(
                        unquote(urlparse(track[mappings['uri']]).path))
                    queries.append(track_id)
                elif 'id' in mappings and track.get(mappings['id']):
                    queries.append(track[mappings['id']])
                elif 'name' in mappings and 'artist' in mappings and track.get(mappings['name']) and track.get(mappings['artist']):
                    query = f"{track[mappings['artist']]} - {track[mappings['name']]}"
                    queries.append(query)
    except Exception as e:
        print(f"Ошибка чтения JSON: {e}")
        raise
    return queries
