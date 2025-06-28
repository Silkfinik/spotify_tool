# import_dialog.py

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QRadioButton, QLineEdit,
    QComboBox, QPushButton, QFileDialog, QDialogButtonBox
)


class ImportDialog(QDialog):
    """
    Диалоговое окно для выбора файла и настроек импорта.
    """

    def __init__(self, playlists: list[dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Импорт треков из файла")
        self.setMinimumWidth(400)

        # Основной макет
        layout = QVBoxLayout(self)

        # --- Выбор файла ---
        file_group = QGroupBox("1. Выберите файл")
        file_layout = QHBoxLayout(file_group)
        self.filepath_edit = QLineEdit()
        self.filepath_edit.setPlaceholderText("Путь к файлу .csv или .json")
        self.filepath_edit.setReadOnly(True)
        self.browse_button = QPushButton("Обзор...")
        file_layout.addWidget(self.filepath_edit)
        file_layout.addWidget(self.browse_button)
        layout.addWidget(file_group)

        # --- Выбор плейлиста ---
        playlist_group = QGroupBox("2. Выберите целевой плейлист")
        playlist_layout = QVBoxLayout(playlist_group)

        self.create_new_radio = QRadioButton("Создать новый плейлист")
        self.create_new_radio.setChecked(True)
        self.new_playlist_name_edit = QLineEdit()
        self.new_playlist_name_edit.setPlaceholderText(
            "Название нового плейлиста")

        self.add_existing_radio = QRadioButton(
            "Добавить в существующий плейлист")
        self.existing_playlist_combo = QComboBox()
        # Заполняем выпадающий список
        for playlist in playlists:
            # Не даем добавлять треки в "Понравившиеся" таким способом
            if playlist['id'] != 'liked_songs':
                self.existing_playlist_combo.addItem(
                    playlist['name'], playlist['id'])

        playlist_layout.addWidget(self.create_new_radio)
        playlist_layout.addWidget(self.new_playlist_name_edit)
        playlist_layout.addWidget(self.add_existing_radio)
        playlist_layout.addWidget(self.existing_playlist_combo)
        layout.addWidget(playlist_group)

        # --- Кнопки OK и Cancel ---
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        # --- Подключение сигналов ---
        self.browse_button.clicked.connect(self.browse_for_file)
        self.create_new_radio.toggled.connect(self.update_widget_states)

        # Устанавливаем начальное состояние виджетов
        self.update_widget_states(True)

    def browse_for_file(self):
        """Открывает диалог выбора файла."""
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите файл для импорта",
            "",
            "CSV и JSON файлы (*.csv *.json)"
        )
        if filename:
            self.filepath_edit.setText(filename)

    def update_widget_states(self, is_create_new_checked):
        """Включает/выключает поля в зависимости от выбора пользователя."""
        self.new_playlist_name_edit.setEnabled(is_create_new_checked)
        self.existing_playlist_combo.setEnabled(not is_create_new_checked)

    def get_import_settings(self):
        """Возвращает словарь с выбранными настройками."""
        if not self.filepath_edit.text():
            return None  # Если файл не выбран

        settings = {
            "filepath": self.filepath_edit.text(),
            "mode": "create" if self.create_new_radio.isChecked() else "add"
        }

        if settings["mode"] == "create":
            settings["target"] = self.new_playlist_name_edit.text()
        else:
            # Получаем ID плейлиста
            settings["target"] = self.existing_playlist_combo.currentData()

        # Проверка, что имя нового плейлиста не пустое
        if settings["mode"] == "create" and not settings["target"]:
            return None

        return settings
