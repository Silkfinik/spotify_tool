# main.py

import sys
import webbrowser
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from functools import partial

from PyQt6.QtWidgets import QApplication, QTableWidgetItem, QFileDialog
from PyQt6.QtCore import QObject, pyqtSignal, Qt

# Импортируем наши классы
from ui_main_window import MainWindow
from auth_manager import AuthManager
from spotify_client import SpotifyClient
from exporter import export_to_csv


class CallbackHandler(BaseHTTPRequestHandler):
    # ... код этого класса остается без изменений ...
    def __init__(self, request, client_address, server, app_instance):
        self.app_instance = app_instance
        super().__init__(request, client_address, server)

    def do_GET(self):
        parsed_path = urlparse(self.path)
        query_params = parse_qs(parsed_path.query)
        if 'code' in query_params:
            auth_code = query_params['code'][0]
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(
                b"<h1>Success!</h1><p>You can close this tab.</p>")
            self.app_instance.code_received_signal.emit(auth_code)
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(
                b"<h1>Error</h1><p>Authorization code not found.</p>")
        threading.Thread(target=self.server.shutdown).start()


class SpotifyApp(QObject):
    code_received_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        try:
            self.auth_manager = AuthManager()
        except ValueError as e:
            print(f"Критическая ошибка: {e}")
            sys.exit(1)

        self.window = MainWindow()
        self.spotify_client = None  # <-- ДОБАВЛЕНО
        # <-- ДОБАВЛЕНО: для хранения данных о плейлистах (id и name)
        self.playlists = []
        self.current_playlist_id = None  # <-- ДОБАВЛЕНО
        self.is_playlist_view = False   # <-- ДОБАВЛЕНО: для отслеживания контекста
        self.current_playlist_name = ""

        # Подключение сигналов к слотам (методам)
        self.window.login_button.clicked.connect(self.start_login)
        self.code_received_signal.connect(self.process_auth_code)
        self.window.playlist_list.itemClicked.connect(
            self.display_tracks)  # <-- НОВЫЙ СИГНАЛ
        self.window.export_button.clicked.connect(self.open_export_dialog)
        self.window.search_button.clicked.connect(
            self.search_and_display_tracks)  # <-- НОВЫЙ СИГНАЛ
        self.window.search_bar.returnPressed.connect(
            self.search_and_display_tracks)  # <-- Удобство: поиск по Enter
        self.window.track_table.customContextMenuRequested.connect(
            self.show_track_context_menu)

    def start_login(self):
        self.start_callback_server()
        auth_url = self.auth_manager.get_auth_url()
        webbrowser.open(auth_url)
        print("Открыта страница входа Spotify в браузере...")

    def start_callback_server(self):
        def handler_factory(*args, **kwargs):
            return CallbackHandler(*args, **kwargs, app_instance=self)
        port = urlparse(self.auth_manager.redirect_uri).port
        server_address = ('127.0.0.1', port)
        httpd = HTTPServer(server_address, handler_factory)
        server_thread = threading.Thread(target=httpd.serve_forever)
        server_thread.daemon = True
        server_thread.start()
        print(
            f"Локальный сервер запущен на порту {port} для перехвата кода...")

    def process_auth_code(self, code):
        print("Код авторизации получен, обмениваем его на токен...")
        try:
            self.auth_manager.get_token(code)
            print("✅ Токен успешно получен и сохранен в кеш.")
            self.window.login_button.setText("✅ Успешно")
            self.window.login_button.setEnabled(False)

            # Создаем клиент Spotify и загружаем плейлисты
            # v-- ИЗМЕНЕНИЕ ЗДЕСЬ --v
            self.spotify_client = SpotifyClient(self.auth_manager.sp_oauth)
            self.load_user_playlists()

        except Exception as e:
            print(f"❌ Ошибка при получении токена: {e}")
            self.window.login_button.setText("Ошибка входа")

    # --> НОВЫЙ МЕТОД <--
    def load_user_playlists(self):
        """Загружает плейлисты пользователя и отображает их в списке."""
        print("Загрузка плейлистов...")
        self.playlists = self.spotify_client.get_user_playlists()
        self.window.playlist_list.clear()  # Очищаем список перед заполнением
        for playlist in self.playlists:
            self.window.playlist_list.addItem(playlist['name'])
        print(f"Загружено {len(self.playlists)} плейлистов.")

    # --> НОВЫЙ МЕТОД <--
    def display_tracks(self, item):
        row = self.window.playlist_list.row(item)
        selected_playlist = self.playlists[row]
        self.current_playlist_id = selected_playlist['id']
        # <-- ДОБАВЛЕНО
        self.current_playlist_name = selected_playlist['name']
        self.is_playlist_view = True

        print(
            f"Загрузка треков для плейлиста '{self.current_playlist_name}'...")
        tracks = self.spotify_client.get_playlist_tracks(playlist_id)

        self.window.track_table.setRowCount(0)
        self.window.track_table.setRowCount(len(tracks))

        for row_num, track_data in enumerate(tracks):
            self.window.track_table.setItem(
                row_num, 0, QTableWidgetItem(track_data['name']))
            self.window.track_table.setItem(
                row_num, 1, QTableWidgetItem(track_data['artist']))
            self.window.track_table.setItem(
                row_num, 2, QTableWidgetItem(track_data['album']))

        # Активируем кнопку экспорта, только если есть треки
        self.window.export_button.setEnabled(
            len(tracks) > 0)  # <-- ИЗМЕНЕНО
        print(f"Отображено {len(tracks)} треков.")
        """Отображает треки выбранного плейлиста в таблице."""
        # Находим, на какой по счету плейлист нажал пользователь
        row = self.window.playlist_list.row(item)
        selected_playlist = self.playlists[row]
        playlist_id = selected_playlist['id']
        playlist_name = selected_playlist['name']

        print(f"Загрузка треков для плейлиста '{playlist_name}'...")
        tracks = self.spotify_client.get_playlist_tracks(playlist_id)

        # Очищаем таблицу перед заполнением
        self.window.track_table.setRowCount(0)
        self.window.track_table.setRowCount(len(tracks))

        # Заполняем таблицу данными
        for row_num, track_data in enumerate(tracks):
            self.window.track_table.setItem(
                row_num, 0, QTableWidgetItem(track_data['name']))
            self.window.track_table.setItem(
                row_num, 1, QTableWidgetItem(track_data['artist']))
            self.window.track_table.setItem(
                row_num, 2, QTableWidgetItem(track_data['album']))

        # После загрузки треков активируем кнопку экспорта
        self.window.export_button.setEnabled(True)
        print(f"Отображено {len(tracks)} треков.")

    def search_and_display_tracks(self):

        self.is_playlist_view = False
        """Выполняет поиск треков и отображает их в таблице."""
        if not self.spotify_client:
            print("Сначала войдите в Spotify.")
            self.window.statusBar().showMessage("Сначала войдите в Spotify.", 3000)
            return

        query = self.window.search_bar.text()
        if not query:
            print("Поисковый запрос не может быть пустым.")
            return

        print(f"Поиск по запросу: '{query}'...")
        tracks = self.spotify_client.search_tracks(query)
        # Обновляем для экспорта
        self.current_playlist_name = f"Результаты поиска по '{query}'"
        self.populate_track_table(tracks)
        print(f"Найдено {len(tracks)} треков.")

    # --> НОВЫЙ ВСПОМОГАТЕЛЬНЫЙ МЕТОД <--
    def populate_track_table(self, tracks: list[dict]):
        """Очищает и заполняет таблицу треков данными."""
        self.window.track_table.setRowCount(0)
        self.window.track_table.setRowCount(len(tracks))

        for row_num, track_data in enumerate(tracks):

            name_item = QTableWidgetItem(track_data['name'])
            name_item.setData(Qt.ItemDataRole.UserRole,
                              track_data['id'])  # Сохраняем ID

            self.window.track_table.setItem(
                row_num, 0, QTableWidgetItem(track_data['name']))
            self.window.track_table.setItem(
                row_num, 1, QTableWidgetItem(track_data['artist']))
            self.window.track_table.setItem(
                row_num, 2, QTableWidgetItem(track_data['album']))

        self.window.export_button.setEnabled(len(tracks) > 0)

    def open_export_dialog(self):
        """
        Открывает диалог сохранения файла и экспортирует данные из таблицы.
        """
        if self.window.track_table.rowCount() == 0:
            print("Нет данных для экспорта.")
            return

        # Предлагаем имя файла на основе названия плейлиста
        default_filename = f"{self.current_playlist_name}.csv"

        # Открываем стандартный диалог сохранения
        filename, _ = QFileDialog.getSaveFileName(
            self.window,
            "Сохранить как...",
            default_filename,
            "CSV Files (*.csv)"
        )

        # Если пользователь выбрал файл и нажал "Сохранить"
        if filename:
            # 1. Собираем заголовки
            headers = [
                self.window.track_table.horizontalHeaderItem(i).text()
                for i in range(self.window.track_table.columnCount())
            ]

            # 2. Собираем данные из всех ячеек таблицы
            data_to_export = [headers]
            for row in range(self.window.track_table.rowCount()):
                row_data = []
                for col in range(self.window.track_table.columnCount()):
                    item = self.window.track_table.item(row, col)
                    row_data.append(item.text() if item else "")
                data_to_export.append(row_data)

            # 3. Вызываем функцию экспорта
            if export_to_csv(data_to_export, filename):
                # Показываем сообщение в статус-баре на 5 секунд
                self.window.statusBar().showMessage(
                    f"Файл успешно сохранен: {filename}", 5000)

    def show_track_context_menu(self, position):
        """Создает и показывает контекстное меню для выделенных треков."""
        selected_items = self.window.track_table.selectedItems()
        if not selected_items:
            return

        # Получаем уникальные ID выделенных треков
        selected_track_ids = list(set(
            self.window.track_table.item(
                item.row(), 0).data(Qt.ItemDataRole.UserRole)
            for item in selected_items
        ))

        menu = self.window.track_table.createStandardContextMenu()

        # 1. Подменю "Добавить в плейлист"
        add_to_playlist_menu = menu.addMenu("Добавить в плейлист")
        for playlist in self.playlists:
            # Нельзя добавить треки в "Понравившиеся" через это меню
            if playlist['id'] == 'liked_songs':
                continue
            action = add_to_playlist_menu.addAction(playlist['name'])
            # Используем partial, чтобы передать аргументы в обработчик
            action.triggered.connect(
                partial(self.add_selected_to_playlist, playlist['id'], selected_track_ids))

        menu.addSeparator()

        # 2. Пункт "Удалить из текущего плейлиста"
        if self.is_playlist_view and self.current_playlist_id != 'liked_songs':
            remove_action = menu.addAction("Удалить из текущего плейлиста")
            remove_action.triggered.connect(
                partial(self.remove_selected_from_playlist, selected_track_ids))

        # 3. Пункт "Добавить/Удалить из Любимых"
        is_liked_list = self.spotify_client.check_if_tracks_are_liked(
            selected_track_ids)
        # Логика для кнопки: если хотя бы один не лайкнут - предлагаем лайкнуть все.
        if not all(is_liked_list):
            like_action = menu.addAction("Добавить в 'Понравившиеся'")
            like_action.triggered.connect(
                partial(self.add_selected_to_liked, selected_track_ids))
        else:
            unlike_action = menu.addAction("Удалить из 'Понравившихся'")
            unlike_action.triggered.connect(
                partial(self.remove_selected_from_liked, selected_track_ids))

        menu.exec(self.window.track_table.viewport().mapToGlobal(position))

    def add_selected_to_playlist(self, playlist_id, track_ids):
        self.spotify_client.add_tracks_to_playlist(playlist_id, track_ids)
        self.window.statusBar().showMessage(f"Треки добавлены в плейлист.", 3000)

    def remove_selected_from_playlist(self, track_ids):
        self.spotify_client.remove_tracks_from_playlist(
            self.current_playlist_id, track_ids)
        self.window.statusBar().showMessage(
            f"Треки удалены из плейлиста. Обновление...", 3000)
        # Обновляем вид, чтобы увидеть изменения
        current_row = self.window.playlist_list.currentRow()
        self.display_tracks_from_playlist(
            self.window.playlist_list.item(current_row))

    def add_selected_to_liked(self, track_ids):
        self.spotify_client.add_tracks_to_liked(track_ids)
        self.window.statusBar().showMessage("Треки добавлены в 'Понравившиеся'.", 3000)

    def remove_selected_from_liked(self, track_ids):
        self.spotify_client.remove_tracks_from_liked(track_ids)
        self.window.statusBar().showMessage("Треки удалены из 'Понравившихся'.", 3000)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    spotify_app = SpotifyApp()

    cached_token = spotify_app.auth_manager.get_cached_token()
    if cached_token:
        print("Обнаружен кешированный токен, автоматический вход...")
        # v-- И ИЗМЕНЕНИЕ ЗДЕСЬ --v
        spotify_app.spotify_client = SpotifyClient(
            spotify_app.auth_manager.sp_oauth)
        spotify_app.load_user_playlists()
        spotify_app.window.login_button.setText("✅ Успешно")
        spotify_app.window.login_button.setEnabled(False)

    spotify_app.window.show()
    sys.exit(app.exec())
