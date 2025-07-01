# paste_text_dialog.py

import os

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QTextEdit, QLabel,
    QDialogButtonBox, QFileDialog
)


class PasteTextDialog(QDialog):
    """
    Диалоговое окно для вставки текста и создания из него CSV-файла.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Импорт из текста")
        self.setMinimumSize(500, 400)

        layout = QVBoxLayout(self)

        info_label = QLabel(
            "Вставьте список треков в поле ниже. "
            "Каждый трек должен быть на новой строке.\n"
            "Идеальный формат: <b>Исполнитель - Название</b>"
        )
        layout.addWidget(info_label)

        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText(
            "Пример:\n"
            "Queen - Bohemian Rhapsody\n"
            "Nirvana - Smells Like Teen Spirit\n"
            "The Beatles - Hey Jude"
        )
        layout.addWidget(self.text_edit)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.process_and_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.csv_filepath = None

    def process_and_accept(self):
        """Анализирует текст и предлагает сохранить его как CSV."""
        text = self.text_edit.toPlainText().strip()
        if not text:
            self.reject()
            return

        lines = text.splitlines()

        default_save_path = os.path.join('data', 'temp_import.csv')

        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить временный CSV-файл",
            default_save_path,  # Используем новый путь
            "CSV Files (*.csv)"
        )

        if not save_path:
            self.reject()
            return

        # Создаем CSV-файл
        try:
            import csv
            with open(save_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['artist', 'name'])  # Заголовки
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue

                    # Пытаемся разделить строку по " - "
                    parts = line.split(' - ', 1)
                    if len(parts) == 2:
                        artist, name = parts
                        writer.writerow([artist.strip(), name.strip()])
                    else:
                        # Если разделить не удалось, считаем всю строку названием
                        writer.writerow(['', line])

            self.csv_filepath = save_path
            self.accept()  # Закрываем диалог с успехом

        except Exception as e:
            print(f"Ошибка при создании временного CSV: {e}")
            self.reject()

    def get_csv_filepath(self):
        """Возвращает путь к созданному CSV-файлу."""
        return self.csv_filepath
