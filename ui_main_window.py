# ui_main_window.py

import sys
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QListWidget,
    QTableWidget,
    QPushButton,
    QHeaderView,
    QLineEdit  # <-- НОВЫЙ ИМПОРТ
)


class MainWindow(QMainWindow):
    """
    Главное окно приложения.
    """

    def __init__(self):
        super().__init__()

        # --- Настройки основного окна ---
        self.setWindowTitle("Экспорт плейлистов Spotify")
        self.setGeometry(100, 100, 1200, 800)
        self.statusBar()

        # --- Центральный виджет и главный макет ---
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # --- Верхняя панель с кнопками ---
        button_layout = QHBoxLayout()
        self.login_button = QPushButton("Войти в Spotify")
        self.import_button = QPushButton("Импорт из файла")
        self.export_button = QPushButton("Экспорт в файл")
        self.export_button.setEnabled(False)
        self.import_button.setEnabled(False)

        button_layout.addWidget(self.login_button)
        button_layout.addWidget(self.import_button)
        button_layout.addWidget(self.export_button)
        button_layout.addStretch()

        # --- Разделитель для двух основных панелей ---
        splitter = QSplitter()

        # --- Левая панель: список плейлистов ---
        self.playlist_list = QListWidget()
        splitter.addWidget(self.playlist_list)
        self.playlist_list.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        splitter.addWidget(self.playlist_list)

        # --> НАЧАЛО НОВОЙ ЛОГИКИ <--
        # Создаем контейнер для правой панели (поиск + таблица)
        right_panel_widget = QWidget()
        right_panel_layout = QVBoxLayout(right_panel_widget)

        # Создаем макет для поиска
        search_layout = QHBoxLayout()
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText(
            "Введите название трека или исполнителя...")
        self.search_button = QPushButton("Найти")

        search_layout.addWidget(self.search_bar)
        search_layout.addWidget(self.search_button)

        # Добавляем макет поиска в правую панель
        right_panel_layout.addLayout(search_layout)
        # --> КОНЕЦ НОВОЙ ЛОГИКИ <--

        # --- Правая панель: таблица треков ---
        self.track_table = QTableWidget()
        self.track_table.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self.track_table.setColumnCount(3)
        self.track_table.setHorizontalHeaderLabels(
            ["Название", "Исполнитель", "Альбом"])

        header = self.track_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.track_table.setAlternatingRowColors(True)

        # Добавляем таблицу в правую панель
        right_panel_layout.addWidget(self.track_table)

        # Добавляем всю правую панель в разделитель
        splitter.addWidget(right_panel_widget)

        # Настройка размеров разделителя
        splitter.setSizes([300, 900])

        # --- Сборка главного макета ---
        main_layout.addLayout(button_layout)
        main_layout.addWidget(splitter)


# Этот блок позволяет запустить файл напрямую для просмотра окна
if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
