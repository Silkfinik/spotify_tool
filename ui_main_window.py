import sys
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QListWidget, QTableWidget, QPushButton, QHeaderView, QLineEdit
)
import qtawesome as qta


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Spotify Manager")
        self.setGeometry(100, 100, 1200, 800)
        self.statusBar()

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        button_layout = QHBoxLayout()
        self.login_button = QPushButton("Войти в Spotify")

        self.import_button = QPushButton(
            qta.icon('fa5s.file-import', color='#E0E0E0'), "")
        self.import_button.setToolTip("Импорт из файла...")
        self.import_button.setEnabled(False)

        self.export_button = QPushButton(
            qta.icon('fa5s.file-csv', color='#E0E0E0'), "")
        self.export_button.setToolTip("Экспорт в файл...")
        self.export_button.setEnabled(False)

        button_layout.addWidget(self.login_button)
        button_layout.addStretch()
        button_layout.addWidget(self.import_button)
        button_layout.addWidget(self.export_button)

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

        self.track_table = QTableWidget()
        self.track_table.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self.track_table.setColumnCount(3)
        self.track_table.setHorizontalHeaderLabels(
            ["Название", "Исполнитель", "Альбом"])

        self.track_table.setSortingEnabled(False)

        self.track_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)

        self.track_table.setShowGrid(True)

        self.track_table.verticalHeader().setVisible(True)

        header = self.track_table.horizontalHeader()

        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

        self.track_table.setColumnWidth(0, 350)
        self.track_table.setColumnWidth(1, 250)

        header.setStretchLastSection(True)

        right_panel_layout.addWidget(self.track_table)

        splitter.addWidget(right_panel_widget)
        splitter.setSizes([300, 900])

        main_layout.addLayout(button_layout)
        main_layout.addWidget(splitter)
