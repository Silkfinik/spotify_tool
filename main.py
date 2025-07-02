import sys
import os
import webbrowser
import threading
import traceback
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from functools import partial
from itertools import islice
import qtawesome as qta

from PyQt6.QtWidgets import QApplication, QTableWidgetItem, QFileDialog, QMenu, QMessageBox, QProgressDialog, QListWidgetItem
from PyQt6.QtCore import QObject, pyqtSignal, QThread, Qt, QTimer
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QProgressBar, QPushButton
from PyQt6.QtWidgets import QProgressDialog

from ui_main_window import MainWindow
from auth_manager import AuthManager
from spotify_client import SpotifyClient
from exporter import export_to_csv, export_to_json, export_to_txt
from export_dialog import ExportDialog
from import_dialog import ImportDialog
from importer import parse_file
from paste_text_dialog import PasteTextDialog

import requests  # <-- ДОБАВЬТЕ ЭТОТ ИМПОРТ


def has_internet_connection():
    """
    Проверяет наличие интернет-соединения, отправляя запрос к надежному серверу.
    """
    try:
        # Отправляем легкий HEAD-запрос с коротким таймаутом (3 секунды)
        requests.head("http://www.google.com", timeout=3)
        return True
    except (requests.ConnectionError, requests.Timeout):
        return False


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
    Универсальный 'рабочий' с сигналами прогресса.
    """
    finished = pyqtSignal(object)
    error = pyqtSignal(tuple)
    progress = pyqtSignal(int, int)  # <-- НОВЫЙ СИГНАЛ (текущий, всего)

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs

    def run(self):
        """Выполняет задачу, передавая в нее колбэки для прогресса и отмены."""
        try:
            thread = QThread.currentThread()

            def cancellation_checker():
                return thread.isInterruptionRequested()

            # Передаем и проверку отмены, и репортер прогресса
            self.kwargs['cancellation_check'] = cancellation_checker
            self.kwargs['progress_callback'] = self.progress.emit

            result = self.fn(*self.args, **self.kwargs)
            if not thread.isInterruptionRequested():
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

        self.thread = None
        self.worker = None

        # --> НОВОЕ: Создаем виджеты для строки состояния заранее <--
        self.status_progress_bar = QProgressBar()
        self.status_progress_bar.setMaximumSize(200, 15)
        # --> ИЗМЕНЕНИЕ: Включаем отображение текста <--
        self.status_progress_bar.setTextVisible(True)
        # --> ДОБАВЛЕНО: Указываем, что в тексте должен быть процент <--
        self.status_progress_bar.setFormat("%p%")
        self.status_progress_bar.hide()

        self.status_cancel_button = QPushButton(
            qta.icon('fa5s.times-circle', color='#E0E0E0'), " Отмена")
        # --> ДОБАВЛЕНО: Устанавливаем уникальное имя объекта для QSS <--
        self.status_cancel_button.setObjectName("StatusBarCancelButton")
        self.status_cancel_button.hide()
        self.status_cancel_button.clicked.connect(self.cancel_task)

        # Подключение сигналов к слотам (методам)
        self.window.login_button.clicked.connect(self.start_login)
        self.window.refresh_button.clicked.connect(self.load_user_playlists)
        self.code_received_signal.connect(self.process_auth_code)
        self.code_received_signal.connect(self.process_auth_code)
        self.window.playlist_list.itemClicked.connect(
            self.display_tracks_from_playlist)
        self.window.playlist_list.customContextMenuRequested.connect(
            self.show_playlist_context_menu)
        self.window.track_table.customContextMenuRequested.connect(
            self.show_track_context_menu)
        self.window.export_button.clicked.connect(self.export_tracks)
        self.window.import_button.clicked.connect(self.open_import_dialog)
        self.window.paste_text_button.clicked.connect(
            self.open_paste_text_dialog)
        self.window.search_button.clicked.connect(
            self.search_and_display_tracks)
        self.window.search_bar.returnPressed.connect(
            self.search_and_display_tracks)

    # --- Обновленная инфраструктура для многопоточности ---

    def run_long_task(self, fn, on_finish, *args, label_text="Выполнение операции..."):
        """Запускает долгую задачу, показывая оверлей и индикатор в строке состояния."""
        if not has_internet_connection():
            self.update_status(
                "❌ Ошибка: отсутствует подключение к интернету.")
            return  # Немедленно выходим, не запуская задачу

        if self.thread and self.thread.isRunning():
            self.cancel_task(silent=True)
            QTimer.singleShot(100, lambda: self.run_long_task(
                fn, on_finish, *args, label_text=label_text))
            return

        # Показываем виджеты в строке состояния
        self.update_status(label_text, timeout=0)
        self.status_progress_bar.setRange(0, 100)
        self.status_progress_bar.setValue(0)
        self.window.statusBar().addPermanentWidget(self.status_progress_bar)
        self.window.statusBar().addPermanentWidget(self.status_cancel_button)
        self.status_progress_bar.show()
        self.status_cancel_button.show()

        # --> ИЗМЕНЕНИЕ: Управляем оверлеем вручную <--
        self.window.overlay.setGeometry(self.window.centralWidget().rect())
        self.window.overlay.setCursor(QCursor(Qt.CursorShape.WaitCursor))
        self.window.overlay.show()
        self.window.overlay.raise_()

        # Создаем и запускаем поток
        self.thread = QThread()
        self.worker = Worker(fn, *args)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(on_finish)
        self.worker.error.connect(self.on_task_error)
        self.worker.progress.connect(self.update_progress)

        # Очистка
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(self.restore_ui)
        self.thread.finished.connect(self.on_thread_finished)

        self.thread.start()

    def restore_ui(self):
        """Восстанавливает интерфейс, скрывая оверлей и виджеты."""
        # --> ИЗМЕНЕНИЕ: Скрываем оверлей и сбрасываем его курсор <--
        self.window.overlay.hide()
        self.window.overlay.unsetCursor()

        self.status_progress_bar.hide()
        self.status_cancel_button.hide()
        self.window.statusBar().removeWidget(self.status_progress_bar)
        self.window.statusBar().removeWidget(self.status_cancel_button)
        self.update_status("Готово.", timeout=2000)

        # Очищаем сообщение в строке состояния
        self.update_status("Готово.", timeout=2000)

    def update_progress(self, current_value, max_value):
        """Слот для обновления прогресс-бара в строке состояния."""
        if max_value > 0:
            percent = int((current_value / max_value) * 100)
            self.status_progress_bar.setValue(percent)

    def on_thread_finished(self):
        self.thread = None
        self.worker = None

    def on_task_error(self, error_info):
        print("Произошла ошибка в рабочем потоке:")
        print(error_info[2])
        self.update_status(f"Ошибка: {error_info[1]}")
        self.restore_ui()

    def cancel_task(self, silent: bool = False):
        if not silent:
            self.update_status("Операция отменена пользователем.")

        if self.thread and self.thread.isRunning():
            self.thread.requestInterruption()
            self.thread.quit()
        else:
            self.restore_ui()

    def update_status(self, message: str, timeout: int = 4000):
        """
        Обновляет строку состояния. Сообщение исчезнет через указанное время.
        Если timeout = 0, сообщение будет постоянным.
        """
        self.window.statusBar().showMessage(message, timeout)

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
        self.window.refresh_button.setEnabled(True)
        self.window.import_button.setEnabled(True)
        self.window.paste_text_button.setEnabled(True)
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
        default_filename = os.path.join(
            'data', f"{self.current_playlist_name}.{settings['format']}")
        filename, _ = QFileDialog.getSaveFileName(
            self.window, "Сохранить как...", default_filename, file_extensions[settings['format']]
        )
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

    # main.py, внутри класса SpotifyApp

    def open_import_dialog(self):
        """Открывает диалог для выбора файла с диска и запускает импорт."""
        if not self.spotify_client:
            return self.update_status("Сначала войдите в Spotify.")

        # 1. Сначала выбираем файл
        filepath, _ = QFileDialog.getOpenFileName(
            self.window,
            "Выберите файл для импорта",
            "data",  # Начальная директория
            "CSV и JSON файлы (*.csv *.json)"
        )

        # Если файл был выбран, переходим к следующему шагу
        if filepath:
            self._show_import_playlist_options(filepath)

    def open_paste_text_dialog(self):
        """Открывает диалог для вставки текста и запускает импорт."""
        if not self.spotify_client:
            return self.update_status("Сначала войдите в Spotify.")

        paste_dialog = PasteTextDialog(self.window)
        if paste_dialog.exec():
            # Если пользователь вставил текст и сохранил временный CSV
            csv_filepath = paste_dialog.get_csv_filepath()
            if csv_filepath:
                # Переходим к тому же самому шагу, что и при импорте из файла
                self._show_import_playlist_options(csv_filepath)

    def _show_import_playlist_options(self, filepath: str):
        """
        Принимает путь к файлу и открывает диалог для выбора плейлиста.
        """
        import os
        dialog = ImportDialog(self.playlists, self.window)

        # Мы программно устанавливаем путь к файлу и делаем поле нередактируемым.
        dialog.filepath_edit.setText(filepath)
        dialog.filepath_edit.setReadOnly(True)
        dialog.browse_button.setEnabled(False)

        # --> ВАШ КОД ВСТАВЛЯЕТСЯ СЮДА <--
        if dialog.exec():
            settings = dialog.get_import_settings()
            if settings:
                # Запускаем первый этап импорта (поиск) в фоновом потоке
                self.run_long_task(
                    self._perform_import,
                    self.on_import_search_finished,  # Указываем, какой метод вызвать по завершении
                    settings,
                    label_text=f"Поиск треков из {os.path.basename(filepath)}..."
                )
            else:
                self.update_status(
                    "Ошибка: не все поля для импорта заполнены.")

    def _perform_import(self, settings: dict, cancellation_check=None, progress_callback=None, **kwargs) -> dict:
        """
        ЭТАП 1: Парсит файл, находит ID треков и определяет целевой плейлист.
        Ничего не добавляет, только собирает информацию.
        """
        try:
            # 1. Парсинг и поиск Spotify ID
            queries_or_ids = parse_file(settings['filepath'])
            total_to_find = len(queries_or_ids)
            if total_to_find == 0:
                raise ValueError("В файле не найдено записей для импорта.")

            found_track_ids = []
            for i, item in enumerate(queries_or_ids):
                if cancellation_check and cancellation_check():
                    raise InterruptedError("Операция отменена.")
                if progress_callback:
                    progress_callback(i + 1, total_to_find)

                if len(item) == 22 and item.isalnum():
                    found_track_ids.append(item)
                else:
                    track_id = self.spotify_client.find_track_id(query=item)
                    if track_id:
                        found_track_ids.append(track_id)

            if not found_track_ids:
                raise ValueError("Не найдено ни одного трека для добавления.")

            # 2. Определение целевого плейлиста
            target_playlist_id = None
            target_playlist_name = ""
            if settings['mode'] == 'create':
                target_playlist_name = settings['target']
                target_playlist_id = self.spotify_client.create_new_playlist(
                    name=target_playlist_name)
                if not target_playlist_id:
                    raise Exception(
                        f"Не удалось создать плейлист '{target_playlist_name}'")
            else:
                target_playlist_id = settings['target']
                # Находим имя существующего плейлиста по его ID
                target_playlist_name = next(
                    (p['name'] for p in self.playlists if p['id'] == target_playlist_id), "Неизвестный плейлист")

            # 3. Возвращаем всю собранную информацию для следующего шага
            return {
                "ok": True,
                "found_ids": found_track_ids,
                "target_id": target_playlist_id,
                "target_name": target_playlist_name,
                "mode": settings['mode']
            }

        except Exception as e:
            traceback.print_exc()
            return {"ok": False, "error": str(e)}

    def on_import_search_finished(self, result: dict):
        """
        ЭТАП 2: Вызывается после поиска треков. Проверяет дубликаты
        ВНУТРИ ФАЙЛА, а затем - с плейлистом.
        """
        if not result.get("ok"):
            return self.update_status(f"Ошибка на этапе поиска: {result.get('error')}")

        found_ids = result['found_ids']
        target_id = result['target_id']
        target_name = result['target_name']

        # --- НАЧАЛО НОВОЙ ЛОГИКИ: Проверка дубликатов внутри файла ---

        # Сохраняем уникальные ID в порядке их появления
        unique_ids_in_file = list(dict.fromkeys(found_ids))
        internal_duplicates_count = len(found_ids) - len(unique_ids_in_file)

        if internal_duplicates_count > 0:
            msg_box = QMessageBox(self.window)
            msg_box.setWindowTitle("Найдены дубликаты в файле")
            msg_box.setText(
                f"Импортируемый файл содержит <b>{internal_duplicates_count}</b> дубликатов.")
            msg_box.setInformativeText("Как поступить с ними?")

            unique_btn = msg_box.addButton(
                "Импортировать только уникальные", QMessageBox.ButtonRole.YesRole)
            all_btn = msg_box.addButton(
                "Импортировать все", QMessageBox.ButtonRole.NoRole)
            msg_box.addButton("Отмена", QMessageBox.ButtonRole.RejectRole)
            msg_box.exec()

            clicked_button = msg_box.clickedButton()
            if clicked_button == unique_btn:
                found_ids = unique_ids_in_file  # Используем только уникальные ID
            elif clicked_button != all_btn:  # Если "Отмена" или окно закрыто
                return self.update_status("Импорт отменен.")

        # --- КОНЕЦ НОВОЙ ЛОГИКИ ---

        # Если добавляем в существующий плейлист, проверяем дубликаты с ним
        if result['mode'] == 'add':
            existing_ids = self.spotify_client.get_playlist_track_ids(
                target_id)
            duplicates_with_playlist = [
                track_id for track_id in found_ids if track_id in existing_ids]

            if duplicates_with_playlist:
                msg_box = QMessageBox(self.window)
                msg_box.setWindowTitle("Найдены дубликаты в плейлисте")
                msg_box.setText(
                    f"В плейлисте «{target_name}» уже есть <b>{len(duplicates_with_playlist)}</b> из импортируемых треков.")
                msg_box.setInformativeText("Добавить дубликаты все равно?")

                add_all_btn = msg_box.addButton(
                    "Добавить все", QMessageBox.ButtonRole.YesRole)
                skip_btn = msg_box.addButton(
                    "Пропустить дубликаты", QMessageBox.ButtonRole.NoRole)
                msg_box.addButton("Отмена", QMessageBox.ButtonRole.RejectRole)
                msg_box.exec()

                clicked_button = msg_box.clickedButton()
                if clicked_button == skip_btn:
                    found_ids = [
                        track_id for track_id in found_ids if track_id not in existing_ids]
                elif clicked_button != add_all_btn:
                    return self.update_status("Импорт отменен.")

        if not found_ids:
            return self.update_status("Нет новых треков для добавления.")

        # ЭТАП 3: Запускаем финальную задачу по добавлению треков
        self.run_long_task(
            self.spotify_client.add_tracks_to_playlist,
            lambda _: self.on_import_add_finished(len(found_ids), target_name),
            target_id,
            found_ids,
            label_text=f"Добавление треков в '{target_name}'..."
        )

    def on_import_add_finished(self, count, playlist_name):
        """Вызывается после завершения добавления треков в плейлист."""
        self.update_status(
            f"Успешно добавлено {count} треков в плейлист '{playlist_name}'.")
        # Обновляем списки на случай создания нового плейлиста или для консистентности
        QTimer.singleShot(100, self.load_user_playlists)

    def confirm_and_delete_playlist(self, playlist_id, playlist_name):
        reply = QMessageBox.warning(self.window, "Подтверждение удаления",
                                    f"Вы уверены, что хотите удалить плейлист <br><b>{playlist_name}</b>?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.run_long_task(self.spotify_client.delete_playlist, self.on_playlist_deleted,
                               playlist_id, label_text=f"Удаление плейлиста '{playlist_name}'...")

    def add_selected_to_playlist(self, playlist_id, track_ids):
        self.run_long_task(
            self.spotify_client.add_tracks_to_playlist,
            # --> ИЗМЕНЕНИЕ: Используем новый обработчик <--
            lambda _: self.on_operation_and_refresh(
                "Треки успешно добавлены. Обновление..."),
            playlist_id,
            track_ids,
            label_text="Добавление треков в плейлист..."
        )

    def remove_selected_from_playlist(self, track_ids):
        self.run_long_task(
            self.spotify_client.remove_tracks_from_playlist,
            # --> ИЗМЕНЕНИЕ: Используем новый обработчик <--
            lambda _: self.on_operation_and_refresh(
                "Треки удалены. Обновление..."),
            self.current_playlist_id,
            track_ids,
            label_text="Удаление треков из плейлиста..."
        )

    def add_selected_to_liked(self, track_ids):
        self.run_long_task(self.spotify_client.add_tracks_to_liked, self.on_like_status_changed,
                           track_ids, label_text="Добавление в 'Понравившиеся'...")

    def remove_selected_from_liked(self, track_ids):
        self.run_long_task(self.spotify_client.remove_tracks_from_liked,
                           self.on_like_status_changed, track_ids, label_text="Удаление из 'Понравившихся'...")

    def on_playlists_loaded(self, playlists):
        """
        Вызывается после загрузки плейлистов. Обновляет список в UI
        и перезагружает треки, если плейлист был выбран.
        """
        # 1. Запоминаем ID текущего выбранного плейлиста, если он есть
        previously_selected_id = self.current_playlist_id

        self.playlists = playlists
        self.window.playlist_list.clear()

        newly_selected_item = None
        for playlist in self.playlists:
            # Создаем новый элемент списка
            item = QListWidgetItem(playlist['name'])
            self.window.playlist_list.addItem(item)

            # 2. Если ID этого плейлиста совпадает с тем, что был выбран ранее,
            # запоминаем новый элемент списка для последующей активации.
            if playlist['id'] == previously_selected_id:
                newly_selected_item = item

        self.update_status(f"Загружено {len(self.playlists)} плейлистов.")

        # 3. Если плейлист был выбран до обновления, выбираем его снова и обновляем треки
        if newly_selected_item:
            # Программно делаем элемент текущим (выделяем его)
            self.window.playlist_list.setCurrentItem(newly_selected_item)

            # Вызываем наш стандартный метод обновления треков.
            # Он уже использует self.current_playlist_id, который остался прежним.
            self.refresh_track_view()

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
        """
        Вызывается после добавления/удаления трека из 'Понравившихся'.
        Обновляет вид, если пользователь сейчас смотрит этот список.
        """
        self.update_status("Статус 'Понравившихся' обновлен.")

        # --> ДОБАВЛЕНО: Проверяем, нужно ли обновить вид <--
        # Если текущий "плейлист" - это 'Понравившиеся треки',
        # то запускаем обновление.
        if self.current_playlist_id == 'liked_songs':
            self.refresh_track_view()

    def on_operation_and_refresh(self, success_message: str):
        """
        Универсальный обработчик: показывает сообщение и запускает обновление вида.
        """
        self.update_status(success_message)
        self.refresh_track_view()

    def on_playlist_deleted(self, success):
        if success:
            self.update_status("Плейлист успешно удален. Обновление списка...")
            QTimer.singleShot(100, self.load_user_playlists)
        else:
            self.update_status("Не удалось удалить плейлист.")

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

        # --> НОВЫЙ ПУНКТ МЕНЮ <--
        find_duplicates_action = menu.addAction("Найти и удалить дубликаты")
        find_duplicates_action.triggered.connect(
            lambda: self.handle_find_duplicates_action(playlist['id'], playlist['name']))

        menu.addSeparator()  # Разделитель для красоты

        delete_action = menu.addAction(
            f"Удалить плейлист '{playlist['name']}'")
        delete_action.triggered.connect(
            lambda: self.confirm_and_delete_playlist(playlist['id'], playlist['name']))

        menu.exec(self.window.playlist_list.viewport().mapToGlobal(position))

    def handle_find_duplicates_action(self, playlist_id, playlist_name):
        """Инициирует поиск дубликатов."""
        self.run_long_task(
            self._find_and_remove_duplicates,
            self.on_duplicates_found,  # Слот для обработки результата
            playlist_id,
            label_text=f"Поиск дубликатов в '{playlist_name}'..."
        )

    # --> НОВЫЙ МЕТОД-ИНИЦИАТОР <--
    def handle_find_duplicates_action(self, playlist_id, playlist_name):
        """Запускает процесс поиска дубликатов для подтверждения."""
        self.run_long_task(
            self._find_duplicates_info,
            self.on_duplicates_info_received,  # Новый слот для обработки результата
            playlist_id,
            label_text=f"Поиск дубликатов в '{playlist_name}'..."
        )

    # --> НОВЫЙ МЕТОД, ВЫПОЛНЯЕМЫЙ В ПОТОКЕ (ТОЛЬКО ЧТЕНИЕ) <--
    def _find_duplicates_info(self, playlist_id: str, cancellation_check=None, progress_callback=None, **kwargs) -> tuple:
        """Находит дубликаты и возвращает информацию о них, ничего не удаляя."""
        from collections import Counter

        all_tracks = self.spotify_client.get_playlist_tracks(
            playlist_id, cancellation_check, progress_callback)
        if cancellation_check and cancellation_check():
            raise InterruptedError("Операция отменена.")

        track_ids = [t['id'] for t in all_tracks if t.get('id')]
        counts = Counter(track_ids)
        num_duplicates = sum(
            count - 1 for count in counts.values() if count > 1)

        # Возвращаем ID плейлиста и количество найденных дубликатов
        return (playlist_id, num_duplicates)

    # --> НОВЫЙ СЛОТ-ОБРАБОТЧИК ДЛЯ ПОКАЗА ДИАЛОГА <--
    def on_duplicates_info_received(self, result):
        """Показывает диалог подтверждения, если дубликаты найдены."""
        if not isinstance(result, tuple):
            self.update_status(
                str(result) if result else "Не удалось получить информацию о дубликатах.")
            return

        playlist_id, num_duplicates = result

        if num_duplicates == 0:
            self.update_status("Дубликаты не найдены.")
            return

        reply = QMessageBox.question(
            self.window,
            "Найдены дубликаты",
            f"Найдено дубликатов: <b>{num_duplicates}</b>. <br><br>Хотите удалить их?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            # Запускаем задачу на реальное удаление
            self.run_long_task(
                self.spotify_client.deduplicate_playlist,
                # --> ИЗМЕНЕНИЕ: Используем новый обработчик <--
                # `result` из deduplicate_playlist - это кол-во удаленных дубликатов
                lambda result: self.on_operation_and_refresh(
                    f"Удалено {result} дубликатов. Обновление..."),
                playlist_id,
                label_text="Удаление дубликатов..."
            )


if __name__ == '__main__':

    os.makedirs('data', exist_ok=True)
    app = QApplication(sys.argv)

    try:
        with open("style.qss", "r") as f:
            app.setStyleSheet(f.read())
    except FileNotFoundError:
        print("Файл style.qss не найден. Будет использован стандартный стиль.")

    spotify_app = SpotifyApp()

    if spotify_app.auth_manager.get_cached_token():
        print("Обнаружен кешированный токен, автоматический вход...")
        spotify_app.window.refresh_button.setEnabled(True)
        spotify_app.on_login_success()

    spotify_app.window.show()
    sys.exit(app.exec())
