# api_key_dialog.py

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QLineEdit, QDialogButtonBox
)


class ApiKeyDialog(QDialog):
    """
    Диалоговое окно для ввода API ключа Gemini.
    """

    def __init__(self, current_key: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("API Ключ для Google Gemini")

        layout = QVBoxLayout(self)

        info_label = QLabel(
            "Пожалуйста, введите ваш API ключ от Google AI Studio.\n"
            "Ключ будет сохранен локально и использован для отправки запросов."
        )
        layout.addWidget(info_label)

        self.key_input = QLineEdit()
        self.key_input.setText(current_key)
        self.key_input.setPlaceholderText("Вставьте ваш API ключ сюда...")
        # Скрываем символы при вводе для безопасности
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.key_input)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def get_api_key(self) -> str:
        """Возвращает введенный пользователем ключ."""
        return self.key_input.text().strip()
