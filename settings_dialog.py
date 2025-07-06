# settings_dialog.py

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSlider,
    QDialogButtonBox
)
from PyQt6.QtCore import Qt


class SettingsDialog(QDialog):
    """
    Диалоговое окно для настроек вида приложения.
    """

    def __init__(self, current_scale_value: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройки вида")

        # Словарь для отображения названий
        self.scale_map_names = {0: 'Маленький', 1: 'Средний', 2: 'Большой'}

        layout = QVBoxLayout(self)

        # Секция для слайдера
        slider_layout = QHBoxLayout()
        self.label = QLabel(
            f"Размер интерфейса: <b>{self.scale_map_names[current_scale_value]}</b>")

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 2)  # 0: Маленький, 1: Средний, 2: Большой
        self.slider.setValue(current_scale_value)
        self.slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.slider.setTickInterval(1)

        slider_layout.addWidget(self.label)
        slider_layout.addWidget(self.slider)
        layout.addLayout(slider_layout)

        # Кнопки OK и Cancel
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        # Подключаем сигнал для обновления текста в реальном времени
        self.slider.valueChanged.connect(self.update_label)

    def update_label(self, value):
        """Обновляет текст метки при движении слайдера."""
        self.label.setText(
            f"Размер интерфейса: <b>{self.scale_map_names[value]}</b>")

    def get_selected_scale_value(self) -> int:
        """Возвращает итоговое значение слайдера."""
        return self.slider.value()
