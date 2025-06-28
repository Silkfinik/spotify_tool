# main.py

import sys
import webbrowser
import threading
import traceback
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from functools import partial
from itertools import islice

from PyQt6.QtWidgets import QApplication, QTableWidgetItem, QFileDialog, QMenu, QMessageBox, QProgressDialog
from PyQt6.QtCore import QObject, pyqtSignal, QThread, Qt, QTimer
from PyQt6.QtGui import QCursor

# Импортируем наши классы
from ui_main_window import MainWindow
from auth_manager import AuthManager
from spotify_client import SpotifyClient
from exporter import export_to_csv, export_to_json, export_to_txt
from import_dialog import ImportDialog


def chunks(iterable, size=100):
    """Разбивает итерируемый объект на части заданного размера."""
    iterator = iter(iterable)
    while chunk := list(islice(iterator, size)):
        yield chunk


class CallbackHandler(BaseHTTPRequestHandler):
    """
    Обработчик для веб-сервера, который принимает редирект от Spotify.
    """

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


class Worker(QObject):
    """
    Универсальный 'рабочий' для выполнения задач в отдельном потоке.
    """
    finished = pyqtSignal(object)
    error = pyqtSignal(tuple)

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs

    def run(self):
        """Выполняет задачу."""
        try:
            result = self.fn(*self.args, **self.kwargs)
            self.finished.emit(result)
        except Exception:
            self.error.emit((sys.exc_info()[0], sys.exc_info()[
                            1], traceback.format_exc()))


class SpotifyApp(QObject):
    """
    Главный класс приложения, связывающий UI и логику.
    """
    code_received_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        try:
            self.auth_manager = AuthManager()
        except ValueError as e:
            print(f"Критическая ошибка: {e}")
            sys.exit(1)

        self.window = MainWindow()
        self.spotify_client = None
        self.playlists = []
        self.current_playlist_id = None
        self.current_playlist_name = ""
        self.is_playlist_view = False

        self.progress_dialog = None
        self.thread = None
        self.worker = None

        # Подключение сигналов к слотам (методам)
        self.window.login_button.clicked.connect(self.start_login)
        self.code_received_signal.connect(self.process_auth_code)
        self.window.playlist_list.itemClicked.connect(
            self.display_tracks_from_playlist)
        self.window.playlist_list.customContextMenuRequested.connect(
            self.show_playlist_context_menu)
        self.window.track_table.customContextMenuRequested.connect(
            self.show_track_context_menu)
        self.window.export_button.clicked.connect(self.export_tracks)
        self.window.import_button.clicked.connect(self.open_import_dialog)
        self.window.search_button.clicked.connect(
            self.search_and_display_tracks)
        self.window.search_bar.returnPressed.connect(
            self.search_and_display_tracks)

    # --- Инфраструктура для многопоточности ---

    def run_long_task(self, fn, on_finish, *args, label_text="Выполнение операции..."):
        """Запускает долгую задачу в отдельном потоке и показывает диалог прогресса."""
        if self.thread and self.thread.isRunning():
            print("Предыдущая операция еще не завершена.")
            return

        self.thread = QThread()
        self.worker = Worker(fn, *args)
        self.worker.moveToThread(self.thread)

        # ... (код создания QProgressDialog без изменений) ...

        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(on_finish)
        self.worker.error.connect(self.on_task_error)

        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(self.restore_ui)

        # --> ДОБАВЛЕНО: Подключаем новый слот для очистки ссылок <--
        self.thread.finished.connect(self.on_thread_finished)

        self.thread.start()
        # ... (код показа диалога и курсора) ...

    # --> НОВЫЙ МЕТОД-СЛОТ <--
    def on_thread_finished(self):
        """Слот, который очищает ссылки на завершенный поток и рабочего."""
        self.thread = None
        self.worker = None

    def restore_ui(self):
        """Восстанавливает курсор и закрывает диалог прогресса."""
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None
        QApplication.restoreOverrideCursor()

    def on_task_error(self, error_info):
        """Обрабатывает ошибку из потока."""
        print("Произошла ошибка в рабочем потоке:")
        print(error_info[2])
        self.update_status(f"Ошибка: {error_info[1]}")
        self.restore_ui()

    def cancel_task(self):
        """Прерывает выполнение фоновой задачи."""
        self.update_status("Операция отменена пользователем.")
        if self.thread and self.thread.isRunning():
            self.thread.requestInterruption()
            self.thread.quit()
            self.thread.wait(500)
        self.restore_ui()

    def update_status(self, message):
        """Обновляет строку состояния."""
        self.window.statusBar().showMessage(message)

    # --- Методы-инициаторы ---

    def start_login(self):
        self.start_callback_server()
        auth_url = self.auth_manager.get_auth_url()
        webbrowser.open(auth_url)
        self.update_status("Ожидание авторизации в браузере...")

    def start_callback_server(self):
        handler_factory = lambda *args, **kwargs: CallbackHandler(
            *args, **kwargs, app_instance=self)
        port = urlparse(self.auth_manager.redirect_uri).port
        server_address = ('127.0.0.1', port)
        httpd = HTTPServer(server_address, handler_factory)
        server_thread = threading.Thread(
            target=httpd.serve_forever, daemon=True)
        server_thread.start()
        print(
            f"Локальный сервер запущен на порту {port} для перехвата кода...")

    def process_auth_code(self, code):
        self.update_status("Код получен, обмен на токен...")
        try:
            self.auth_manager.get_token(code)
            self.on_login_success()
        except Exception as e:
            self.on_task_error((type(e), e, traceback.format_exc()))

    def on_login_success(self):
        self.update_status("Успешный вход. Загрузка данных...")
        self.window.login_button.setText("✅ Успешно")
        self.window.login_button.setEnabled(False)
        self.window.import_button.setEnabled(True)
        self.spotify_client = SpotifyClient(self.auth_manager.sp_oauth)
        self.load_user_playlists()

    def load_user_playlists(self):
        self.run_long_task(self.spotify_client.get_user_playlists,
                           self.on_playlists_loaded, label_text="Загрузка плейлистов...")

    def display_tracks_from_playlist(self, item):
        row = self.window.playlist_list.row(item)
        selected_playlist = self.playlists[row]
        self.current_playlist_id = selected_playlist['id']
        self.current_playlist_name = selected_playlist['name']
        self.is_playlist_view = True
        self.refresh_track_view()

    def refresh_track_view(self):
        if self.is_playlist_view and self.current_playlist_id:
            self.run_long_task(self.spotify_client.get_playlist_tracks, self.on_tracks_loaded,
                               self.current_playlist_id, label_text=f"Загрузка треков из '{self.current_playlist_name}'...")

    def search_and_display_tracks(self):
        if not self.spotify_client:
            return self.update_status("Сначала войдите в Spotify.")
        query = self.window.search_bar.text()
        if not query:
            return
        self.is_playlist_view = False
        self.current_playlist_name = f"Результаты поиска по '{query}'"
        self.run_long_task(self.spotify_client.search_tracks, self.on_tracks_loaded,
                           query, label_text=f"Поиск по запросу: '{query}'...")

    def export_tracks(self):
        if self.window.track_table.rowCount() == 0:
            return self.update_status("Нет данных для экспорта.")
        dialog = ExportDialog(self.window)
        if not dialog.exec():
            return
        settings = dialog.get_settings()
        if not settings:
            return self.update_status("Ошибка: не все поля для импорта заполнены.")
        track_data = [{
            "id": self.window.track_table.item(row, 0).data(Qt.ItemDataRole.UserRole),
            "name": self.window.track_table.item(row, 0).text(),
            "artist": self.window.track_table.item(row, 1).text(),
            "album": self.window.track_table.item(row, 2).text(),
        } for row in range(self.window.track_table.rowCount())]
        file_extensions = {
            "csv": "CSV Files (*.csv)", "json": "JSON Files (*.json)", "txt": "Text Files (*.txt)"}
        default_filename = f"{self.current_playlist_name}.{settings['format']}"
        filename, _ = QFileDialog.getSaveFileName(
            self.window, "Сохранить как...", default_filename, file_extensions[settings['format']])
        if filename:
            exporter_fn, args = None, ()
            if settings['format'] == 'csv':
                exporter_fn, args = export_to_csv, (
                    track_data, filename, settings['columns'])
            elif settings['format'] == 'json':
                exporter_fn, args = export_to_json, (track_data, filename)
            elif settings['format'] == 'txt':
                exporter_fn, args = export_to_txt, (
                    track_data, filename, settings['template'])
            if exporter_fn:
                self.run_long_task(exporter_fn, self.on_export_finished, *args,
                                   label_text=f"Экспорт в {settings['format'].upper()}...")

    def open_import_dialog(self):
        if not self.spotify_client:
            return self.update_status("Сначала войдите в Spotify.")
        dialog = ImportDialog(self.playlists, self.window)
        if dialog.exec():
            settings = dialog.get_import_settings()
            if settings:
                self.run_long_task(self._perform_import, self.on_import_finished,
                                   settings, label_text="Импорт треков из файла...")
            else:
                self.update_status(
                    "Ошибка: не все поля для импорта заполнены.")

    def _perform_import(self, settings: dict) -> str:
        try:
            queries_or_ids = parse_file(settings['filepath'])
            total_to_find = len(queries_or_ids)
            if total_to_find == 0:
                return "В файле не найдено записей для импорта."
            found_track_ids = [item for item in queries_or_ids if len(
                item) == 22 and item.isalnum()]
            queries_to_search = [
                item for item in queries_or_ids if item not in found_track_ids]
            for query in queries_to_search:
                track_id = self.spotify_client.find_track_id(query)
                if track_id:
                    found_track_ids.append(track_id)
            if not found_track_ids:
                return "Не найдено ни одного трека для добавления."
            if settings['mode'] == 'create':
                playlist_name = settings['target']
                target_playlist_id = self.spotify_client.create_new_playlist(
                    playlist_name)
                if not target_playlist_id:
                    raise Exception(
                        f"Не удалось создать плейлист '{playlist_name}'")
            else:
                target_playlist_id = settings['target']
            for id_chunk in chunks(found_track_ids, 100):
                self.spotify_client.add_tracks_to_playlist(
                    target_playlist_id, id_chunk)
            return f"Успешно добавлено {len(found_track_ids)} из {total_to_find} треков."
        except Exception as e:
            traceback.print_exc()
            return f"Ошибка: {e}"

    def confirm_and_delete_playlist(self, playlist_id, playlist_name):
        reply = QMessageBox.warning(self.window, "Подтверждение удаления",
                                    f"Вы уверены, что хотите удалить плейлист <br><b>{playlist_name}</b>?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.run_long_task(self.spotify_client.delete_playlist, self.on_playlist_deleted,
                               playlist_id, label_text=f"Удаление плейлиста '{playlist_name}'...")

    def add_selected_to_playlist(self, playlist_id, track_ids):
        self.run_long_task(self.spotify_client.add_tracks_to_playlist, lambda _: self.update_status(
            "Треки успешно добавлены."), playlist_id, track_ids, label_text="Добавление треков в плейлист...")

    def remove_selected_from_playlist(self, track_ids):
        self.run_long_task(self.spotify_client.remove_tracks_from_playlist, self.on_playlist_modified,
                           self.current_playlist_id, track_ids, label_text="Удаление треков из плейлиста...")

    def add_selected_to_liked(self, track_ids):
        self.run_long_task(self.spotify_client.add_tracks_to_liked, self.on_like_status_changed,
                           track_ids, label_text="Добавление в 'Понравившиеся'...")

    def remove_selected_from_liked(self, track_ids):
        self.run_long_task(self.spotify_client.remove_tracks_from_liked,
                           self.on_like_status_changed, track_ids, label_text="Удаление из 'Понравившихся'...")

    # --- Методы-слоты для обработки результатов ---

    def on_playlists_loaded(self, playlists):
        self.playlists = playlists
        self.window.playlist_list.clear()
        for playlist in self.playlists:
            self.window.playlist_list.addItem(playlist['name'])
        self.update_status(f"Загружено {len(self.playlists)} плейлистов.")

    def on_tracks_loaded(self, tracks):
        self.populate_track_table(tracks)
        self.update_status(f"Загружено {len(tracks)} треков.")

    def on_export_finished(self, success):
        self.update_status(
            "Экспорт успешно завершен." if success else "Ошибка во время экспорта.")

    def on_import_finished(self, result_message: str):
        self.update_status(result_message)
        QTimer.singleShot(100, self.load_user_playlists)

    def on_like_status_changed(self, _):
        self.update_status("Статус 'Понравившихся' обновлен.")

    def on_playlist_modified(self, _):
        self.update_status("Плейлист изменен. Обновление вида...")
        self.refresh_track_view()

    def on_playlist_deleted(self, success):
        if success:
            self.update_status("Плейлист успешно удален. Обновление списка...")
            QTimer.singleShot(100, self.load_user_playlists)
        else:
            self.update_status("Не удалось удалить плейлист.")

    # --- Основная логика и UI ---

    def populate_track_table(self, tracks: list[dict]):
        self.window.track_table.setRowCount(0)
        self.window.track_table.setRowCount(len(tracks))
        for row_num, track_data in enumerate(tracks):
            name_item = QTableWidgetItem(track_data['name'])
            name_item.setData(Qt.ItemDataRole.UserRole, track_data.get('id'))
            self.window.track_table.setItem(row_num, 0, name_item)
            self.window.track_table.setItem(
                row_num, 1, QTableWidgetItem(track_data['artist']))
            self.window.track_table.setItem(
                row_num, 2, QTableWidgetItem(track_data['album']))
        self.window.export_button.setEnabled(len(tracks) > 0)

    def show_track_context_menu(self, position):
        selected_items = self.window.track_table.selectedItems()
        if not selected_items:
            return
        selected_track_ids = list(set(self.window.track_table.item(
            item.row(), 0).data(Qt.ItemDataRole.UserRole) for item in selected_items))
        selected_track_ids = [tid for tid in selected_track_ids if tid]
        if not selected_track_ids:
            return
        menu = QMenu(self.window.track_table)
        add_to_playlist_menu = menu.addMenu("Добавить в плейлист")
        for playlist in self.playlists:
            if playlist['id'] == 'liked_songs':
                continue
            action = add_to_playlist_menu.addAction(playlist['name'])
            action.triggered.connect(
                partial(self.add_selected_to_playlist, playlist['id'], selected_track_ids))
        menu.addSeparator()
        if self.is_playlist_view and self.current_playlist_id != 'liked_songs':
            remove_action = menu.addAction("Удалить из текущего плейлиста")
            remove_action.triggered.connect(
                partial(self.remove_selected_from_playlist, selected_track_ids))
        try:
            is_liked_list = self.spotify_client.check_if_tracks_are_liked(
                selected_track_ids)
            if not all(is_liked_list):
                like_action = menu.addAction("Добавить в 'Понравившиеся'")
                like_action.triggered.connect(
                    partial(self.add_selected_to_liked, selected_track_ids))
            else:
                unlike_action = menu.addAction("Удалить из 'Понравившихся'")
                unlike_action.triggered.connect(
                    partial(self.remove_selected_from_liked, selected_track_ids))
        except Exception as e:
            print(f"Не удалось проверить статус 'Понравившихся': {e}")
        menu.exec(self.window.track_table.viewport().mapToGlobal(position))

    def show_playlist_context_menu(self, position):
        item = self.window.playlist_list.itemAt(position)
        if not item:
            return
        row = self.window.playlist_list.row(item)
        playlist = self.playlists[row]
        if playlist['id'] == 'liked_songs':
            return
        menu = QMenu(self.window.playlist_list)
        delete_action = menu.addAction(
            f"Удалить плейлист '{playlist['name']}'")
        delete_action.triggered.connect(
            lambda: self.confirm_and_delete_playlist(playlist['id'], playlist['name']))
        menu.exec(self.window.playlist_list.viewport().mapToGlobal(position))


# --- Точка входа в приложение ---
if __name__ == '__main__':
    app = QApplication(sys.argv)
    spotify_app = SpotifyApp()
    if spotify_app.auth_manager.get_cached_token():
        print("Обнаружен кешированный токен, автоматический вход...")
        spotify_app.on_login_success()
    spotify_app.window.show()
    sys.exit(app.exec())
