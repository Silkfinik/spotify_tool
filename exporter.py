# exporter.py

import csv


def export_to_csv(track_data: list[list], filename: str):
    """
    Экспортирует данные о треках в CSV-файл.

    Args:
        track_data (list[list]): Список списков с данными (включая заголовки).
        filename (str): Полный путь к файлу для сохранения.
    """
    try:
        # Используем utf-8-sig, чтобы Excel корректно распознавал кириллицу
        with open(filename, 'w', newline='', encoding='utf-8-sig') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerows(track_data)
        print(f"Данные успешно экспортированы в {filename}")
        return True
    except Exception as e:
        print(f"Ошибка при записи в CSV-файл: {e}")
        return False
