# export_dialog.py

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QComboBox, QGroupBox,
    QCheckBox, QLineEdit, QDialogButtonBox
)


class ExportDialog(QDialog):
    """
    Диалоговое окно для выбора настроек экспорта.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройки экспорта")

        # Основной макет
        layout = QVBoxLayout(self)

        # --- Выбор формата ---
        format_layout = QHBoxLayout()
        self.format_combo = QComboBox()
        self.format_combo.addItems(["CSV", "JSON", "TXT"])
        format_layout.addWidget(self.format_combo)
        layout.addLayout(format_layout)

        # --- Настройки для CSV ---
        self.csv_group = QGroupBox("Настройки CSV")
        csv_layout = QVBoxLayout(self.csv_group)
        self.csv_columns = {
            "name": QCheckBox("Название трека"),
            "artist": QCheckBox("Исполнитель"),
            "album": QCheckBox("Альбом")
        }
        for checkbox in self.csv_columns.values():
            checkbox.setChecked(True)  # По умолчанию все выбраны
            csv_layout.addWidget(checkbox)
        layout.addWidget(self.csv_group)

        # --- Настройки для TXT ---
        self.txt_group = QGroupBox("Настройки TXT")
        txt_layout = QVBoxLayout(self.txt_group)
        self.txt_template = QLineEdit()
        self.txt_template.setText("{artist} - {name}")  # Шаблон по умолчанию
        txt_layout.addWidget(self.txt_template)
        layout.addWidget(self.txt_group)

        # --- Кнопки OK и Cancel ---
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        # Подключаем сигнал для скрытия/показа опций
        self.format_combo.currentTextChanged.connect(
            self.update_options_visibility)
        # Устанавливаем начальное состояние видимости
        self.update_options_visibility(self.format_combo.currentText())

    def update_options_visibility(self, text):
        """Показывает или скрывает опции в зависимости от выбранного формата."""
        self.csv_group.setVisible(text == "CSV")
        self.txt_group.setVisible(text == "TXT")

    def get_settings(self):
        """Возвращает выбранные пользователем настройки."""
        settings = {
            "format": self.format_combo.currentText().lower()
        }
        if settings["format"] == "csv":
            settings["columns"] = [
                key for key, checkbox in self.csv_columns.items() if checkbox.isChecked()]
        elif settings["format"] == "txt":
            settings["template"] = self.txt_template.text()
        return settings
