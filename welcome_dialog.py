# welcome_dialog.py

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QCheckBox, QDialogButtonBox
)
from PyQt6.QtCore import Qt


class WelcomeDialog(QDialog):
    """
    Диалоговое окно с приветствием и подсказками по использованию.
    """

    def __init__(self, font_size: int, show_checkbox: bool = True, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Добро пожаловать в Spotify Manager!")
        self.setMinimumWidth(500)

        dialog_font = self.font()
        dialog_font.setPointSize(font_size)
        self.setFont(dialog_font)

        layout = QVBoxLayout(self)
        tips_text = """
        <h3>Ключевые возможности:</h3>
        <ul>
            <li><b>AI Ассистент (🪄):</b> Нажмите на иконку волшебной палочки, чтобы создать плейлист по текстовому описанию или найти треки, похожие на существующий плейлист.</li>
            <li><b>Кэширование (☁️):</b> Нажмите на иконку облака, чтобы загрузить все ваши плейлисты в кэш для мгновенного доступа.</li>
            <li><b>Настройки вида (Вид -> Настройки...):</b> Настройте размер шрифтов и обложек для максимального удобства.</li>
            <li><b>Контекстное меню:</b> Нажмите правой кнопкой мыши на трек или плейлист, чтобы увидеть доступные действия.</li>
        </ul>
        """
        info_label = QLabel(tips_text)
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # --> ИЗМЕНЕНИЕ: Создаем галочку только если это нужно <--
        self.dont_show_again_checkbox = None
        if show_checkbox:
            self.dont_show_again_checkbox = QCheckBox(
                "Больше не показывать это окно")
            layout.addWidget(self.dont_show_again_checkbox)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)

    def should_show_again(self) -> bool:
        """Возвращает True, если окно нужно показывать снова."""
        # Если галочки не было, ничего не меняем. Если была - проверяем ее состояние.
        if self.dont_show_again_checkbox:
            return not self.dont_show_again_checkbox.isChecked()
        return True
