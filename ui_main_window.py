# ui_main_window.py

import sys
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QListWidget, QTableWidget, QPushButton, QHeaderView, QLineEdit, QFrame
)
from PyQt6.QtGui import QAction
import qtawesome as qta


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Spotify Manager")
        self.setGeometry(100, 100, 1400, 800)
        self.statusBar()

        menu_bar = self.menuBar()
        view_menu = menu_bar.addMenu("Вид")
        self.show_covers_action = QAction(
            "Показывать обложки", self, checkable=True)
        view_menu.addAction(self.show_covers_action)

        view_menu.addSeparator()

        # 2. НОВЫЙ ПУНКТ МЕНЮ для вызова окна настроек
        self.settings_action = QAction("Настройки вида...", self)
        view_menu.addAction(self.settings_action)

        # Создаем единый центральный виджет
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Весь интерфейс теперь будет в одном главном макете
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # --- Верхняя панель с кнопками ---
        button_layout = QHBoxLayout()
        self.login_button = QPushButton("Войти в Spotify")
        # --> НОВАЯ КНОПКА <--
        self.refresh_button = QPushButton(
            qta.icon('fa5s.sync-alt', color='#E0E0E0'), "")
        self.refresh_button.setToolTip("Обновить список плейлистов")
        self.refresh_button.setEnabled(False)  # Будет неактивна до входа
        self.cache_all_button = QPushButton(
            qta.icon('fa5s.cloud-download-alt', color='#E0E0E0'), "")
        self.cache_all_button.setToolTip("Загрузить все плейлисты в кэш")
        self.cache_all_button.setEnabled(False)
        self.import_button = QPushButton(
            qta.icon('fa5s.file-import', color='#E0E0E0'), "")

        self.ai_button = QPushButton(
            qta.icon('fa5s.magic', color='#E0E0E0'), "")
        self.ai_button.setToolTip("AI Ассистент плейлистов")
        self.ai_button.setEnabled(False)

        self.import_button.setToolTip("Импорт из файла...")
        self.import_button.setEnabled(False)
        self.paste_text_button = QPushButton(
            qta.icon('fa5s.paste', color='#E0E0E0'), "")
        self.paste_text_button.setToolTip("Импорт из текста...")
        self.paste_text_button.setEnabled(False)
        self.export_button = QPushButton(
            qta.icon('fa5s.file-csv', color='#E0E0E0'), "")
        self.export_button.setToolTip("Экспорт в файл...")
        self.export_button.setEnabled(False)
        button_layout.addWidget(self.login_button)
        button_layout.addWidget(self.refresh_button)
        button_layout.addWidget(self.cache_all_button)
        button_layout.addStretch()
        button_layout.addWidget(self.ai_button)
        button_layout.addStretch()
        button_layout.addWidget(self.import_button)
        button_layout.addWidget(self.paste_text_button)
        button_layout.addWidget(self.export_button)
        main_layout.addLayout(button_layout)

        # --- Разделитель ---
        splitter = QSplitter()
        self.playlist_list = QListWidget()
        self.playlist_list.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        splitter.addWidget(self.playlist_list)

        right_panel_widget = QWidget()
        right_panel_layout = QVBoxLayout(right_panel_widget)
        right_panel_layout.setContentsMargins(0, 0, 0, 0)
        search_layout = QHBoxLayout()
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText(
            "Введите название трека или исполнителя...")
        self.search_button = QPushButton(
            qta.icon('fa5s.search', color='#E0E0E0'), "")
        self.search_button.setToolTip("Найти")
        search_layout.addWidget(self.search_bar)
        search_layout.addWidget(self.search_button)
        right_panel_layout.addLayout(search_layout)

        # --- Правая панель: таблица треков ---
        self.track_table = QTableWidget()
        self.track_table.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)

        # --> ИЗМЕНЕНО: Добавляем колонку для обложек (всего 4) <--
        self.track_table.setColumnCount(4)
        self.track_table.setHorizontalHeaderLabels(
            ["", "Название", "Исполнитель", "Альбом"])

        self.track_table.setSortingEnabled(False)
        self.track_table.setShowGrid(True)
        self.track_table.verticalHeader().setVisible(True)
        self.track_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)

        header = self.track_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

        # --> ИЗМЕНЕНО: Настраиваем ширину новых колонок <--
        self.track_table.setColumnWidth(0, 48)  # Колонка для обложки 48х48
        header.setSectionResizeMode(
            0, QHeaderView.ResizeMode.Fixed)  # Фиксированный размер
        self.track_table.setColumnWidth(1, 350)  # Название
        self.track_table.setColumnWidth(2, 250)  # Исполнитель
        header.setStretchLastSection(True)  # Альбом растягивается

        self.track_table.setColumnHidden(0, True)

        # --> ДОБАВЛЕНО: Устанавливаем высоту строк по умолчанию <--
        self.track_table.verticalHeader().setDefaultSectionSize(48)

        right_panel_layout.addWidget(self.track_table)
        splitter.addWidget(right_panel_widget)
        splitter.setSizes([300, 900])
        main_layout.addWidget(splitter)

        # --> НОВАЯ ЛОГИКА: Создаем оверлей как дочерний элемент центрального виджета <--
        self.overlay = QFrame(self.centralWidget())
        self.overlay.setObjectName("Overlay")
        self.overlay.hide()

    def resizeEvent(self, event):
        """Этот метод автоматически вызывается при изменении размера окна."""
        super().resizeEvent(event)
        # Обновляем размер оверлея, чтобы он соответствовал центральному виджету
        self.overlay.setGeometry(self.centralWidget().rect())
