# settings_dialog.py

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QDialogButtonBox, QFormLayout, QComboBox,
    QLabel, QSlider, QWidget, QHBoxLayout
)
from PyQt6.QtCore import Qt


class SettingsDialog(QDialog):
    """
    Диалоговое окно для настроек вида приложения.
    """

    def __init__(self, current_settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройки вида")
        self.setMinimumWidth(400)
        self.settings = current_settings.copy()  # Работаем с копией

        # 1. Создаем главный макет БЕЗ родителя
        main_layout = QVBoxLayout()

        # 2. Создаем макет для формы настроек
        form_layout = QFormLayout()
        font_sizes = [str(i) for i in range(8, 15)]  # Размеры от 8pt до 14pt

        # --- Наполняем форму настроек ---
        self.sidebar_font_combo = self._create_font_combo(
            font_sizes, self.settings.get('sidebar_font_size', 10))
        form_layout.addRow("Шрифт боковой панели:", self.sidebar_font_combo)

        self.table_font_combo = self._create_font_combo(
            font_sizes, self.settings.get('table_font_size', 11))
        form_layout.addRow("Шрифт таблицы треков:", self.table_font_combo)

        self.cover_size_slider = QSlider(Qt.Orientation.Horizontal)
        self.cover_size_slider.setRange(32, 80)
        self.cover_size_slider.setValue(self.settings.get('cover_size', 48))
        self.cover_size_label = QLabel(
            f"{self.settings.get('cover_size', 48)}px")
        self.cover_size_slider.valueChanged.connect(
            lambda v: self.cover_size_label.setText(f"{v}px"))

        size_widget = QWidget()
        size_hbox = QHBoxLayout(size_widget)
        size_hbox.setContentsMargins(0, 0, 0, 0)
        size_hbox.addWidget(self.cover_size_slider)
        size_hbox.addWidget(self.cover_size_label)
        form_layout.addRow("Размер обложек:", size_widget)

        # 3. Добавляем макет формы в главный макет
        main_layout.addLayout(form_layout)

        # 4. Создаем и добавляем кнопки в главный макет
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.button(
            QDialogButtonBox.StandardButton.Ok).setText("Применить")
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)

        # 5. Устанавливаем единственный главный макет для всего диалогового окна
        self.setLayout(main_layout)

    def _create_font_combo(self, sizes: list[str], current_size: int):
        """Вспомогательный метод для создания выпадающего списка."""
        combo = QComboBox()
        combo.addItems(sizes)
        combo.setCurrentText(str(current_size))
        return combo

    def get_new_settings(self) -> dict:
        """Собирает и возвращает новые настройки."""
        self.settings['sidebar_font_size'] = int(
            self.sidebar_font_combo.currentText())
        self.settings['table_font_size'] = int(
            self.table_font_combo.currentText())
        self.settings['cover_size'] = self.cover_size_slider.value()
        return self.settings
