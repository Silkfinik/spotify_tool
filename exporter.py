# exporter.py

import csv
import json


def export_to_csv(track_data: list[dict], filename: str, fieldnames: list[str], **kwargs):
    try:
        with open(filename, 'w', newline='', encoding='utf-8-sig') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for track in track_data:
                row_to_write = {key: track.get(key, "") for key in fieldnames}
                writer.writerow(row_to_write)
        print(f"Данные успешно экспортированы в {filename}")
        return True
    except Exception as e:
        print(f"Ошибка при записи в CSV-файл: {e}")
        return False


def export_to_json(track_data: list[dict], filename: str, **kwargs):
    try:
        with open(filename, 'w', encoding='utf-8') as jsonfile:
            json.dump(track_data, jsonfile, ensure_ascii=False, indent=4)
        print(f"Данные успешно экспортированы в {filename}")
        return True
    except Exception as e:
        print(f"Ошибка при записи в JSON-файл: {e}")
        return False


def export_to_txt(track_data: list[dict], filename: str, template_string: str, **kwargs):
    try:
        with open(filename, 'w', encoding='utf-8') as txtfile:
            for track in track_data:
                try:
                    line = template_string.format(**track) + '\n'
                    txtfile.write(line)
                except KeyError as e:
                    print(
                        f"В шаблоне указан неверный ключ: {e}. Пропуск строки.")
        print(f"Данные успешно экспортированы в {filename}")
        return True
    except Exception as e:
        print(f"Ошибка при записи в TXT-файл: {e}")
        return False
