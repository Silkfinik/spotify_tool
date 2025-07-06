# ai_dialog.py

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget, QLabel, QPlainTextEdit,
    QPushButton, QTableWidget, QHeaderView, QComboBox, QFormLayout
)
from PyQt6.QtCore import pyqtSignal, Qt
import qtawesome as qta


class AiDialog(QDialog):
    """
    Диалоговое окно для взаимодействия с AI-ассистентом.
    """
    # Сигналы, которые окно будет отправлять в основной код
    generate_from_prompt_requested = pyqtSignal(str, str)  # prompt, model_name
    generate_from_playlist_requested = pyqtSignal(
        str, str)  # playlist_id, model_name
    change_api_key_requested = pyqtSignal()
    add_selected_to_playlist_requested = pyqtSignal(
        list)  # list of track dicts

    def __init__(self, playlists: list[dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI Ассистент плейлистов")
        self.setMinimumSize(700, 600)

        # --- Основной макет ---
        main_layout = QVBoxLayout(self)

        # --- Верхняя панель с выбором модели и сменой ключа ---
        top_panel_layout = QHBoxLayout()
        top_panel_layout.addWidget(QLabel("Модель AI:"))
        self.model_combo = QComboBox()
        self.model_combo.addItems(
            ['gemini-pro', 'gemini-1.5-flash'])  # Доступные модели
        top_panel_layout.addWidget(self.model_combo)
        top_panel_layout.addStretch()
        self.change_key_button = QPushButton(
            qta.icon('fa5s.key', color='#E0E0E0'), " Сменить ключ API")
        top_panel_layout.addWidget(self.change_key_button)
        main_layout.addLayout(top_panel_layout)

        # --- Вкладки ---
        tabs = QTabWidget()

        # Вкладка 1: Генерация по тексту
        prompt_tab = QWidget()
        prompt_layout = QVBoxLayout(prompt_tab)
        prompt_label = QLabel(
            "Опишите плейлист, который вы хотите получить (настроение, жанр, похожие исполнители):")
        self.prompt_edit = QPlainTextEdit()
        self.prompt_edit.setPlaceholderText(
            "например: энергичная рок-музыка для тренировки в зале, похожая на AC/DC")
        self.generate_from_prompt_button = QPushButton(
            "Сгенерировать по описанию")
        prompt_layout.addWidget(prompt_label)
        prompt_layout.addWidget(self.prompt_edit)
        prompt_layout.addWidget(self.generate_from_prompt_button)
        tabs.addTab(prompt_tab, "Создать по описанию")

        # Вкладка 2: Поиск похожих
        similar_tab = QWidget()
        similar_layout = QFormLayout(similar_tab)
        similar_label = QLabel("Выберите плейлист, чтобы найти похожие треки:")
        self.playlist_combo = QComboBox()
        for p in playlists:
            self.playlist_combo.addItem(p['name'], p['id'])
        self.generate_from_playlist_button = QPushButton("Найти похожие")
        similar_layout.addRow(similar_label)
        similar_layout.addRow("Плейлист:", self.playlist_combo)
        similar_layout.addRow(self.generate_from_playlist_button)
        tabs.addTab(similar_tab, "Найти похожие")

        main_layout.addWidget(tabs)

        # --- Таблица для результатов ---
        results_label = QLabel("Рекомендации AI:")
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(2)
        self.results_table.setHorizontalHeaderLabels(
            ["Исполнитель", "Название"])
        self.results_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        self.results_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self.results_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        self.results_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)

        # --- Кнопки действий ---
        bottom_buttons_layout = QHBoxLayout()
        self.add_to_playlist_button = QPushButton(
            "Добавить выбранное в плейлист...")
        self.add_to_playlist_button.setEnabled(False)
        close_button = QPushButton("Закрыть")
        bottom_buttons_layout.addStretch()
        bottom_buttons_layout.addWidget(self.add_to_playlist_button)
        bottom_buttons_layout.addWidget(close_button)

        main_layout.addWidget(results_label)
        main_layout.addWidget(self.results_table)
        main_layout.addLayout(bottom_buttons_layout)

        # --- Подключение сигналов ---
        self.generate_from_prompt_button.clicked.connect(
            self.emit_prompt_request)
        self.generate_from_playlist_button.clicked.connect(
            self.emit_playlist_request)
        self.results_table.itemSelectionChanged.connect(
            self.update_add_button_state)
        self.change_key_button.clicked.connect(self.change_api_key_requested)
        self.add_to_playlist_button.clicked.connect(
            self.emit_add_selected_request)
        close_button.clicked.connect(self.accept)

    def emit_prompt_request(self):
        prompt_text = self.prompt_edit.toPlainText().strip()
        model_name = self.model_combo.currentText()
        if prompt_text:
            self.generate_from_prompt_requested.emit(prompt_text, model_name)
            self.lock_ui_for_generation()

    def emit_playlist_request(self):
        playlist_id = self.playlist_combo.currentData()
        model_name = self.model_combo.currentText()
        if playlist_id:
            self.generate_from_playlist_requested.emit(playlist_id, model_name)
            self.lock_ui_for_generation()

    def emit_add_selected_request(self):
        """Собирает данные выделенных треков и отправляет сигнал."""
        selected_rows = sorted(list(set(item.row()
                               for item in self.results_table.selectedItems())))
        tracks_to_add = []
        for row in selected_rows:
            artist = self.results_table.item(row, 0).text()
            name = self.results_table.item(row, 1).text()
            tracks_to_add.append({'artist': artist, 'name': name})

        if tracks_to_add:
            self.add_selected_to_playlist_requested.emit(tracks_to_add)

    def lock_ui_for_generation(self):
        """Блокирует UI на время работы AI."""
        self.generate_from_prompt_button.setEnabled(False)
        self.generate_from_prompt_button.setText("Генерация...")
        self.generate_from_playlist_button.setEnabled(False)
        self.generate_from_playlist_button.setText("Анализ...")
        self.results_table.setRowCount(0)
        self.add_to_playlist_button.setEnabled(False)

    def unlock_ui_after_generation(self):
        """Разблокирует UI после получения ответа."""
        self.generate_from_prompt_button.setEnabled(True)
        self.generate_from_prompt_button.setText("Сгенерировать по описанию")
        self.generate_from_playlist_button.setEnabled(True)
        self.generate_from_playlist_button.setText("Найти похожие")

    def update_add_button_state(self):
        """Активирует кнопку 'Добавить', если в таблице выбраны треки."""
        self.add_to_playlist_button.setEnabled(
            len(self.results_table.selectedItems()) > 0)
