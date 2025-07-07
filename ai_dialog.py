# ai_dialog.py

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget, QLabel, QPlainTextEdit,
    QPushButton, QTableWidget, QHeaderView, QComboBox, QFormLayout, QCheckBox, QLineEdit
)
from PyQt6.QtWidgets import QTableWidgetItem
from PyQt6.QtCore import pyqtSignal, Qt
import qtawesome as qta


class AiDialog(QDialog):
    """
    Диалоговое окно для взаимодействия с AI-ассистентом.
    """
    # Сигналы, которые окно будет отправлять в основной код
    generate_from_prompt_requested = pyqtSignal(
        str, str, int)  # prompt, model_name, num_tracks
    # playlist_id, model_name, num_tracks, refining_prompt
    generate_from_playlist_requested = pyqtSignal(str, str, int, str)
    change_api_key_requested = pyqtSignal()
    show_all_models_toggled = pyqtSignal(bool)
    add_selected_to_playlist_requested = pyqtSignal(
        list)  # list of track dicts

    def __init__(self, playlists: list[dict], available_models: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI Ассистент плейлистов")
        self.setMinimumSize(700, 600)

        # --- Основной макет ---
        main_layout = QVBoxLayout(self)

        # --- Верхняя панель с выбором модели и сменой ключа ---
        self.show_all_models_checkbox = QCheckBox("Показать все")
        self.show_all_models_checkbox.setToolTip(
            "Показать полный список доступных моделей, включая экспериментальные")
        top_panel_layout = QHBoxLayout()
        top_panel_layout.addWidget(QLabel("Модель AI:"))
        self.model_combo = QComboBox()
        if available_models:
            self.model_combo.addItems(available_models)
        else:
            self.model_combo.addItem("Модели не найдены")
            self.model_combo.setEnabled(False)
        top_panel_layout.addWidget(self.model_combo)
        top_panel_layout.addWidget(self.show_all_models_checkbox)
        top_panel_layout.addStretch()
        self.change_key_button = QPushButton(
            qta.icon('fa5s.key', color='#E0E0E0'), " Сменить ключ API")
        top_panel_layout.addWidget(self.change_key_button)
        main_layout.addLayout(top_panel_layout)

        # --- Вкладки ---
        tabs = QTabWidget()

        # --- Вкладка 1: Генерация по тексту ---
        prompt_tab = QWidget()
        prompt_layout = QFormLayout(prompt_tab)

        self.prompt_edit = QPlainTextEdit()
        self.prompt_edit.setPlaceholderText(
            "например: энергичная рок-музыка для тренировки в зале")

        self.prompt_num_tracks_combo = QComboBox()
        self.prompt_num_tracks_combo.addItems(
            [str(i) for i in range(5, 31, 5)])  # 5, 10, 15... 30

        self.generate_from_prompt_button = QPushButton(
            "Сгенерировать по описанию")

        prompt_layout.addRow("Опишите плейлист:", self.prompt_edit)
        prompt_layout.addRow("Количество треков:",
                             self.prompt_num_tracks_combo)
        prompt_layout.addRow(self.generate_from_prompt_button)
        tabs.addTab(prompt_tab, "Создать по описанию")

        # --- Вкладка 2: Поиск похожих ---
        similar_tab = QWidget()
        similar_layout = QFormLayout(similar_tab)

        self.playlist_combo = QComboBox()
        for p in playlists:
            self.playlist_combo.addItem(p['name'], p['id'])

        self.refining_prompt_edit = QLineEdit()
        self.refining_prompt_edit.setPlaceholderText(
            "(необязательно) например: добавь больше женского вокала")

        self.similar_num_tracks_combo = QComboBox()
        self.similar_num_tracks_combo.addItems(
            [str(i) for i in range(5, 31, 5)])

        self.generate_from_playlist_button = QPushButton("Найти похожие")

        similar_layout.addRow("Выберите плейлист:", self.playlist_combo)
        similar_layout.addRow("Уточняющий запрос:", self.refining_prompt_edit)
        similar_layout.addRow("Количество треков:",
                              self.similar_num_tracks_combo)
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
        self.show_all_models_checkbox.toggled.connect(
            self.show_all_models_toggled)
        self.add_to_playlist_button.clicked.connect(
            self.emit_add_selected_request)
        close_button.clicked.connect(self.accept)

    def emit_prompt_request(self):
        prompt_text = self.prompt_edit.toPlainText().strip()
        model_name = self.model_combo.currentText()
        num_tracks = int(self.prompt_num_tracks_combo.currentText())
        if prompt_text:
            self.generate_from_prompt_requested.emit(
                prompt_text, model_name, num_tracks)
            self.lock_ui_for_generation()

    def emit_playlist_request(self):
        playlist_id = self.playlist_combo.currentData()
        model_name = self.model_combo.currentText()
        num_tracks = int(self.similar_num_tracks_combo.currentText())
        refining_prompt = self.refining_prompt_edit.text().strip()
        if playlist_id:
            self.generate_from_playlist_requested.emit(
                playlist_id, model_name, num_tracks, refining_prompt)
            self.lock_ui_for_generation()

    def emit_add_selected_request(self):
        """Собирает ID выделенных треков и отправляет сигнал."""
        selected_rows = sorted(list(set(item.row()
                               for item in self.results_table.selectedItems())))
        track_ids_to_add = []
        for row in selected_rows:
            # Получаем ID, сохраненный в ячейке с названием трека
            id_item = self.results_table.item(row, 1)
            if id_item and id_item.data(Qt.ItemDataRole.UserRole):
                track_ids_to_add.append(id_item.data(Qt.ItemDataRole.UserRole))

        if track_ids_to_add:
            self.add_selected_to_playlist_requested.emit(track_ids_to_add)

    # --> НОВЫЙ МЕТОД для заполнения таблицы <--
    def populate_results_table(self, tracks: list[dict]):
        """Заполняет таблицу результатами от AI."""
        self.results_table.setRowCount(0)
        self.results_table.setRowCount(len(tracks))
        for i, track in enumerate(tracks):
            artist_item = QTableWidgetItem(track['artist'])
            name_item = QTableWidgetItem(track['name'])
            # Сохраняем ID трека в данных ячейки, чтобы потом его использовать
            name_item.setData(Qt.ItemDataRole.UserRole, track.get('id'))

            self.results_table.setItem(i, 0, artist_item)
            self.results_table.setItem(i, 1, name_item)

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
