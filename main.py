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
import json
from settings_dialog import SettingsDialog

from PyQt6.QtWidgets import QApplication, QTableWidgetItem, QFileDialog, QMenu, QMessageBox, QProgressDialog, QListWidgetItem
from PyQt6.QtCore import QObject, pyqtSignal, QThread, Qt, QTimer, QSize
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QProgressBar, QPushButton
from PyQt6.QtWidgets import QProgressDialog
from PyQt6.QtGui import QIcon
from PyQt6.QtGui import QPixmap

from ui_main_window import MainWindow
from auth_manager import AuthManager
from spotify_client import SpotifyClient
from exporter import export_to_csv, export_to_json, export_to_txt
from export_dialog import ExportDialog
from import_dialog import ImportDialog
from importer import parse_file
from paste_text_dialog import PasteTextDialog

import requests  # <-- ДОБАВЬТЕ ЭТОТ ИМПОРТ

from ai_assistant import AIAssistant
from api_key_dialog import ApiKeyDialog
from ai_dialog import AiDialog


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
        """Выполняет задачу, передавая колбэки и обрабатывая отмену."""
        try:
            thread = QThread.currentThread()

            def cancellation_checker():
                return thread.isInterruptionRequested()

            self.kwargs['cancellation_check'] = cancellation_checker
            self.kwargs['progress_callback'] = self.progress.emit

            result = self.fn(*self.args, **self.kwargs)

            # Если задача не была прервана, отправляем сигнал о завершении
            if not thread.isInterruptionRequested():
                self.finished.emit(result)

        except InterruptedError as e:
            # --> НОВЫЙ БЛОК: Ловим наше "запланированное" исключение <--
            # Это не ошибка, а штатное прерывание. Просто выводим сообщение и тихо завершаемся.
            print(f"Рабочий поток прерван пользователем: {e}")
            # Мы не отправляем сигнал error, так как это не ошибка.

        except Exception:
            # Этот блок теперь будет ловить только настоящие, непредвиденные ошибки
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
        self.ai_assistant = None
        self.playlists = []
        self.current_playlist_id = None
        self.current_playlist_name = ""
        self.is_playlist_view = False

        self.cache_file = os.path.join('.app_cache', 'cache.json')
        self.covers_dir = os.path.join('.app_cache', 'covers')
        self.settings_file = os.path.join('.app_cache', 'settings.json')
        self.settings = {}
        self.load_settings()

        # Инициализируем кэши
        self.playlist_cache = {}
        self.track_cache = {}

        # --> НОВОЕ: Загружаем кэш из файла при запуске <--

        self.load_cache()

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

        self.apply_startup_settings()

        # Подключение сигналов к слотам (методам)
        self.window.login_button.clicked.connect(self.start_login)
        self.window.refresh_button.clicked.connect(self.load_user_playlists)
        self.window.cache_all_button.clicked.connect(self.cache_all_playlists)
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
        self.window.show_covers_action.toggled.connect(
            self.toggle_cover_visibility)
        self.window.settings_action.triggered.connect(
            self.open_settings_dialog)
        self.window.ai_assistant_action.triggered.connect(
            self.open_ai_assistant_dialog)
        self.window.show_covers_action.setChecked(
            self.settings.get('show_covers', False))

    # --- Логика AI Ассистента ---

    def open_ai_assistant_dialog(self):
        """
        Инициирует открытие AI ассистента, предварительно загружая список моделей.
        """
        if not self.spotify_client:
            return self.update_status("Сначала войдите в Spotify.")

        api_key = self.settings.get('gemini_api_key')
        if not api_key:
            if not self.prompt_for_api_key():
                return
            api_key = self.settings.get('gemini_api_key')

        try:
            # Инициализируем ассистента здесь, один раз перед запросами
            self.ai_assistant = AIAssistant(api_key)
        except Exception as e:
            self.update_status(f"Ошибка инициализации AI: {e}")
            return

        # Запускаем фоновую задачу на получение списка моделей
        self.run_long_task(
            self.ai_assistant.list_supported_models,
            self._on_ai_models_loaded,  # Новый слот-обработчик
            label_text="Получение списка AI моделей..."
        )

    def _on_ai_models_loaded(self, models: list):
        """
        Вызывается после загрузки списка моделей и открывает главный диалог AI.
        """
        if not isinstance(models, list):
            self.update_status("Не удалось загрузить список AI моделей.")
            return

        # Создаем и показываем диалог, передав ему свежий список моделей
        dialog = AiDialog(self.playlists, models, self.window)

        dialog.generate_from_prompt_requested.connect(
            lambda p, m: self.handle_ai_generation(
                dialog, prompt=p, model_name=m)
        )
        dialog.generate_from_playlist_requested.connect(
            lambda pid, m: self.handle_ai_generation(
                dialog, playlist_id=pid, model_name=m)
        )
        dialog.add_selected_to_playlist_requested.connect(
            self.add_ai_tracks_to_playlist)
        dialog.change_api_key_requested.connect(self.prompt_for_api_key)
        dialog.exec()

    def prompt_for_api_key(self) -> bool:
        """Открывает диалог для ввода/смены ключа API."""
        current_key = self.settings.get('gemini_api_key', "")
        dialog = ApiKeyDialog(current_key, self.window)
        if dialog.exec():
            new_key = dialog.get_api_key()
            if new_key:
                self.settings['gemini_api_key'] = new_key
                self.save_settings()  # Сразу сохраняем
                self.update_status("Ключ API успешно сохранен.")
                return True
        return False

    def handle_ai_generation(self, dialog: AiDialog, **kwargs):
        """Инициирует фоновую задачу для генерации и поиска треков."""
        self.run_long_task(
            self._ai_generation_worker,
            lambda r: self.on_ai_generation_finished(dialog, r),
            kwargs,  # Передаем все аргументы (prompt, playlist_id, model_name)
            label_text="Обращение к AI..."
        )

    def _ai_generation_worker(self, ai_params: dict, **kwargs) -> list:
        """Рабочий метод: общается с AI, ищет треки в Spotify."""
        # 1. Инициализируем ассистента с ключом
        api_key = self.settings.get('gemini_api_key')
        if not api_key:
            raise ValueError("Ключ API Gemini не найден.")
        self.ai_assistant = AIAssistant(api_key)

        recommendations = []
        model_name = ai_params.get('model_name')

        # --- Логика для разных режимов AI ---
        if 'prompt' in ai_params:
            recommendations = self.ai_assistant.get_recommendations_from_prompt(
                ai_params['prompt'], model_name
            )
        elif 'playlist_id' in ai_params:
            # --> НАЧАЛО ИСПРАВЛЕНИЯ <--
            # Используем "умную" загрузку, чтобы получить данные о треках
            playlist_id = ai_params['playlist_id']

            # 1. Получаем все ID треков из плейлиста
            track_ids = self.spotify_client.get_playlist_track_ids(playlist_id)

            # 2. Находим, для каких треков у нас еще нет данных в кэше
            new_ids_to_fetch = [
                tid for tid in track_ids if tid not in self.track_cache]

            # 3. Если есть новые треки, догружаем их детали и обновляем кэш
            if new_ids_to_fetch:
                new_details = self.spotify_client.get_tracks_details(
                    new_ids_to_fetch)
                self.track_cache.update(new_details)

            # 4. Собираем полный список данных о треках из нашего кэша
            playlist_tracks = [self.track_cache[tid]
                               for tid in track_ids if tid in self.track_cache]

            # 5. Отправляем готовые данные в AI для анализа
            recommendations = self.ai_assistant.get_recommendations_from_playlist(
                playlist_tracks, model_name
            )
            # --> КОНЕЦ ИСПРАВЛЕНИЯ <--

        if not recommendations:
            raise ValueError("AI не вернул рекомендации.")

        # Ищем каждый рекомендованный трек в Spotify
        found_tracks = []
        for query in recommendations:
            track_id = self.spotify_client.find_track_id(query)
            if track_id:
                parts = query.split(' - ', 1)
                artist = parts[0]
                name = parts[1] if len(parts) > 1 else ""
                found_tracks.append(
                    {'id': track_id, 'artist': artist, 'name': name})

        return found_tracks

    def on_ai_generation_finished(self, dialog: AiDialog, tracks: list):
        """Вызывается после завершения работы AI, обновляет UI диалога."""
        dialog.unlock_ui_after_generation()
        if isinstance(tracks, list):
            dialog.populate_results_table(tracks)
            self.update_status(f"AI предложил {len(tracks)} треков.")
        else:
            self.update_status("Ошибка при генерации рекомендаций.")

    def add_ai_tracks_to_playlist(self, track_ids: list[str]):
        """Обрабатывает добавление AI треков в плейлист."""
        print(f"Запрос на добавление треков: {track_ids}")
        # Открываем стандартный диалог импорта, но без выбора файла
        import_dialog = ImportDialog(self.playlists, self.window)
        if import_dialog.exec():
            settings = import_dialog.get_import_settings()
            if settings:
                target_id = settings['target']
                if settings['mode'] == 'create':
                    # Создаем плейлист, затем добавляем треки
                    new_id = self.spotify_client.create_new_playlist(
                        settings['target'])
                    if new_id:
                        self.run_long_task(self.spotify_client.add_tracks_to_playlist, lambda r: self.on_import_add_finished(
                            len(track_ids), settings['target'], new_id), new_id, track_ids)
                else:
                    # Добавляем в существующий
                    self.run_long_task(self.spotify_client.add_tracks_to_playlist, lambda r: self.on_import_add_finished(
                        len(track_ids), "выбранный плейлист", target_id), target_id, track_ids)

    def load_settings(self):
        """Загружает детальные настройки из файла."""
        defaults = {
            'gemini_api_key': '',
            'show_covers': False,
            'sidebar_font_size': 10,
            'table_font_size': 11,
            'cover_size': 48,
        }
        if not os.path.exists(self.settings_file):
            self.settings = defaults
            return
        try:
            with open(self.settings_file, 'r', encoding='utf-8') as f:
                self.settings = json.load(f)
            # Убедимся, что все ключи на месте
            for key, value in defaults.items():
                self.settings.setdefault(key, value)
        except Exception:
            self.settings = defaults

    def save_settings(self):
        """Сохраняет текущие настройки в файл."""
        try:
            # Обновляем настройку перед сохранением
            self.settings['show_covers'] = self.window.show_covers_action.isChecked()
            # `ui_scale_value` уже обновлен в self.settings при нажатии "Ок" в диалоге

            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=4)
            print("Настройки сохранены.")
        except IOError as e:
            print(f"Ошибка сохранения настроек: {e}")

    # --> НОВЫЙ МЕТОД, который применяется только при старте <--
    def apply_startup_settings(self):
        """Применяет все детальные настройки к интерфейсу при запуске."""
        s = self.settings
        # Настройка обложек
        self.window.show_covers_action.setChecked(s.get('show_covers', False))
        self.window.track_table.setColumnHidden(
            0, not s.get('show_covers', False))

        # Настройка размеров обложек и строк
        size = s.get('cover_size', 48)
        self.window.track_table.verticalHeader().setDefaultSectionSize(size)
        self.window.track_table.setColumnWidth(0, size)
        self.window.track_table.setIconSize(QSize(size, size))

        # Установка динамических свойств для QSS
        self.window.playlist_list.setProperty(
            "fontSize", s.get('sidebar_font_size', 10))
        self.window.track_table.setProperty(
            "fontSize", s.get('table_font_size', 11))

        # Применяем стили ко всему окну
        for widget in [self.window.playlist_list, self.window.track_table]:
            widget.style().unpolish(widget)
            widget.style().polish(widget)

    # --> НОВЫЙ МЕТОД для вызова окна настроек <--
    def open_settings_dialog(self):
        """Открывает новое окно детальных настроек."""
        dialog = SettingsDialog(self.settings, self.window)
        if dialog.exec():
            new_settings = dialog.get_new_settings()
            # Сравниваем словари, чтобы понять, были ли изменения
            if new_settings != self.settings:
                self.settings = new_settings
                QMessageBox.information(
                    self.window,
                    "Настройки сохранены",
                    "Изменения вступят в силу после перезапуска приложения."
                )

    def load_cache(self):
        """Загружает кэш плейлистов и треков из файла."""
        if not os.path.exists(self.cache_file):
            print("Файл кэша не найден. Будет создан новый.")
            return

        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                cached_data = json.load(f)
                self.playlist_cache = cached_data.get('playlist_cache', {})
                self.track_cache = cached_data.get('track_cache', {})
                print(
                    f"Кэш успешно загружен. Загружено {len(self.playlist_cache)} плейлистов и {len(self.track_cache)} треков.")
        except (json.JSONDecodeError, IOError) as e:
            print(f"Ошибка при чтении файла кэша: {e}. Кэш будет сброшен.")
            self.playlist_cache = {}
            self.track_cache = {}

    def save_cache(self):
        """Сохраняет текущий кэш в файл."""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                cache_to_save = {
                    'playlist_cache': self.playlist_cache,
                    'track_cache': self.track_cache
                }
                json.dump(cache_to_save, f, indent=4)
                print("Кэш успешно сохранен.")
        except IOError as e:
            print(f"Ошибка при сохранении кэша: {e}")

    def display_tracks_from_playlist(self, item):
        """ФАЗА 1 (Инициатор): Запускает быструю проверку snapshot_id."""
        row = self.window.playlist_list.row(item)
        playlist = self.playlists[row]
        self.current_playlist_id = playlist['id']
        self.current_playlist_name = playlist['name']
        self.is_playlist_view = True

        # Запускаем короткую задачу только для проверки состояния кэша
        self.run_long_task(
            self.spotify_client.get_playlist_snapshot_id,
            self._on_snapshot_received,  # Переходим к Фазе 2
            self.current_playlist_id,
            label_text="Проверка плейлиста..."
        )

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

    def _sync_cached_playlists_worker(self, playlists_from_server, cancellation_check=None, progress_callback=None, **kwargs):
        """
        Рабочий метод: проходит по списку плейлистов с сервера и обновляет
        кэш только для тех, которые уже были кэшированы и изменились.
        Возвращает список ID обновленных плейлистов.
        """
        cached_playlist_ids = set(self.playlist_cache.keys())
        playlists_to_check = [p for p in playlists_from_server if p.get(
            'id') in cached_playlist_ids]

        updated_ids = []  # <-- Список для хранения ID обновленных плейлистов

        total_to_check = len(playlists_to_check)
        if total_to_check == 0:
            return {"message": "Нет кэшированных плейлистов для синхронизации.", "updated_ids": []}

        print("--- ЗАПУСК СИНХРОНИЗАЦИИ КЭША ---")

        for i, playlist in enumerate(playlists_to_check):
            playlist_id = playlist.get('id')
            if cancellation_check and cancellation_check():
                raise InterruptedError("Синхронизация отменена.")

            if progress_callback:
                progress_callback(i, total_to_check)

            current_snapshot_id = self.spotify_client.get_playlist_snapshot_id(
                playlist_id)
            cached_snapshot_id = self.playlist_cache[playlist_id].get(
                'snapshot_id')

            if current_snapshot_id != cached_snapshot_id:
                print(
                    f"-> Плейлист '{playlist.get('name')}' изменен. Обновление кэша...")
                self._update_one_playlist_in_cache(
                    playlist_id, cancellation_check=cancellation_check)
                updated_ids.append(playlist_id)  # <-- Добавляем ID в список
            else:
                print(
                    f"-> Плейлист '{playlist.get('name')}' не изменился. Пропуск.")

        return {
            "message": f"Синхронизация завершена. Проверено {total_to_check} кэшированных плейлистов.",
            "updated_ids": updated_ids
        }

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
        self.window.cache_all_button.setEnabled(True)
        self.window.import_button.setEnabled(True)
        self.window.paste_text_button.setEnabled(True)
        self.spotify_client = SpotifyClient(self.auth_manager.sp_oauth)
        self.load_user_playlists()

    def load_user_playlists(self):
        self.run_long_task(self.spotify_client.get_user_playlists,
                           self.on_playlists_loaded, label_text="Загрузка плейлистов...")

    def on_tracks_loaded(self, tracks):
        """
        ФАЗА 4 (Финал): Отображает любые полученные треки и, если нужно,
        запускает фоновую загрузку обложек.
        """
        if not isinstance(tracks, list):
            # Обрабатываем случай, когда вместо списка треков пришло сообщение об ошибке
            self.update_status(str(tracks))
            self.populate_track_table([])  # Очищаем таблицу в случае ошибки
            return

        # 1. Сразу отображаем текстовую информацию, чтобы интерфейс был отзывчивым
        self.populate_track_table(tracks)
        self.update_status(f"Загружено {len(tracks)} треков.")

        # 2. Если включен режим показа обложек, запускаем их фоновую дозагрузку
        if self.window.show_covers_action.isChecked():
            print("Режим обложек включен, запускаю проверку и дозагрузку...")
            self.run_long_task(
                self._download_covers_worker,
                self.on_covers_downloaded,  # Указываем, что делать после загрузки
                label_text="Загрузка обложек..."
            )

    def on_sync_finished(self, result):
        """Вызывается после завершения синхронизации кэша."""
        if not isinstance(result, dict):
            self.update_status(str(result))
            return

        # Показываем итоговое сообщение
        self.update_status(result.get("message", "Синхронизация завершена."))

        # Проверяем, был ли обновлен текущий открытый плейлист
        updated_ids = result.get("updated_ids", [])
        if self.current_playlist_id and self.current_playlist_id in updated_ids:
            print(
                f"Текущий плейлист ({self.current_playlist_id}) был обновлен. Перезагрузка вида...")
            self.refresh_track_view()

    def _on_snapshot_received(self, current_snapshot_id):
        """ФАЗА 2 (Решение): Вызывается после получения snapshot_id."""
        playlist_id = self.current_playlist_id
        cached_playlist = self.playlist_cache.get(playlist_id)

        # Сценарий А: КЭШ-ХИТ. Отображаем мгновенно из кэша.
        if cached_playlist and cached_playlist.get('snapshot_id') == current_snapshot_id:
            print(f"КЭШ-ХИТ для плейлиста {playlist_id}. Загрузка из кэша.")
            track_ids = cached_playlist['track_ids']
            tracks_to_display = [self.track_cache[tid]
                                 for tid in track_ids if tid in self.track_cache]
            # Напрямую вызываем финальный слот
            self.on_tracks_loaded(tracks_to_display)
            return

        # Сценарий Б: КЭШ-ПРОМАХ. Запускаем долгую задачу для загрузки данных.
        print(f"КЭШ-ПРОМАХ для плейлиста {playlist_id}. Загрузка данных...")
        self.run_long_task(
            self._fetch_and_cache_playlist,
            self.on_tracks_loaded,
            playlist_id,
            current_snapshot_id,
            label_text=f"Загрузка треков из '{self.current_playlist_name}'..."
        )

    def _search_tracks_worker(self, query, cancellation_check=None, progress_callback=None, **kwargs):
        """
        Рабочий метод для поиска: находит ID, догружает детали из кэша/сети.
        """
        # 1. Получаем список ID по поисковому запросу
        found_ids = self.spotify_client.search_tracks(query, **kwargs)
        if not found_ids:
            return []

        # 2. Находим, информацию о каких треках нам нужно загрузить
        new_ids_to_fetch = [
            tid for tid in found_ids if tid not in self.track_cache]

        # 3. Если есть новые треки, загружаем их детали
        if new_ids_to_fetch:
            # Здесь мы не можем показать детальный прогресс, так как не знаем заранее, сколько треков найдем
            print(
                f"Поиск нашел {len(found_ids)} треков, из них {len(new_ids_to_fetch)} новых. Загрузка деталей...")
            new_details = self.spotify_client.get_tracks_details(
                new_ids_to_fetch)
            self.track_cache.update(new_details)

        # 4. Собираем итоговый список для отображения из глобального кэша
        return [self.track_cache[tid] for tid in found_ids if tid in self.track_cache]

    def _fetch_and_cache_playlist(self, playlist_id, snapshot_id, cancellation_check=None, progress_callback=None, **kwargs):
        """ФАЗА 3 (Рабочий): Загружает все необходимые данные и обновляет кэши."""
        track_ids = self.spotify_client.get_playlist_track_ids(
            playlist_id, cancellation_check, progress_callback)
        if cancellation_check and cancellation_check():
            raise InterruptedError("Отменено.")

        self.playlist_cache[playlist_id] = {
            "snapshot_id": snapshot_id, "track_ids": track_ids}
        new_track_ids = [
            tid for tid in track_ids if tid not in self.track_cache]

        if new_track_ids:
            new_track_details = self.spotify_client.get_tracks_details(
                new_track_ids)
            self.track_cache.update(new_track_details)

        return [self.track_cache[tid] for tid in track_ids if tid in self.track_cache]

    def cache_all_playlists(self):
        """Инициирует процесс кэширования всех плейлистов."""
        # Передаем копию списка плейлистов, чтобы избежать проблем с многопоточностью
        playlists_to_cache = list(self.playlists)
        self.run_long_task(
            self._cache_all_playlists_worker,
            self.on_cache_all_finished,
            playlists_to_cache,
            label_text="Кэширование всех плейлистов..."
        )

    def _cache_all_playlists_worker(self, playlists_to_cache, cancellation_check=None, progress_callback=None, **kwargs):
        """
        Рабочий метод: проходит по всем плейлистам и обновляет их кэш при необходимости.
        """
        total_playlists = len(playlists_to_cache)
        for i, playlist in enumerate(playlists_to_cache):
            if cancellation_check and cancellation_check():
                return "Кэширование отменено."

            # Сообщаем о прогрессе (какой плейлист обрабатываем)
            if progress_callback:
                progress_callback(i, total_playlists)

            # Мы могли бы добавить проверку snapshot_id здесь для еще большей оптимизации,
            # но для простоты просто вызываем обновление.
            self._update_one_playlist_in_cache(
                playlist['id'], cancellation_check=cancellation_check)

        return f"Кэширование завершено. Обработано {total_playlists} плейлистов."

    def on_cache_all_finished(self, result_message):
        """Вызывается после завершения кэширования."""
        self.update_status(result_message)

    def _update_one_playlist_in_cache(self, playlist_id, cancellation_check=None, progress_callback=None):
        """
        Основная логика: загружает треки для ОДНОГО плейлиста и обновляет оба кэша.
        Возвращает готовый для отображения список треков.
        """
        current_snapshot_id = self.spotify_client.get_playlist_snapshot_id(
            playlist_id)

        track_ids = self.spotify_client.get_playlist_track_ids(
            playlist_id, cancellation_check, progress_callback)
        if cancellation_check and cancellation_check():
            raise InterruptedError("Отменено.")

        self.playlist_cache[playlist_id] = {
            "snapshot_id": current_snapshot_id, "track_ids": track_ids}
        new_track_ids = [
            tid for tid in track_ids if tid not in self.track_cache]

        if new_track_ids:
            new_track_details = self.spotify_client.get_tracks_details(
                new_track_ids)
            self.track_cache.update(new_track_details)

        return [self.track_cache[tid] for tid in track_ids if tid in self.track_cache]

    def _download_covers_for_tracks(self, tracks_to_check: list[dict], cancellation_check=None, progress_callback=None):
        """
        Вспомогательный метод, который скачивает обложки для переданного списка треков.
        Предполагается, что он выполняется внутри Worker'а.
        """
        os.makedirs(self.covers_dir, exist_ok=True)

        # Находим треки, для которых нужно скачать обложки
        tracks_to_download = [
            track for track in tracks_to_check
            if track.get('cover_url') and not track.get('cover_path')
        ]

        total_to_download = len(tracks_to_download)
        for i, track in enumerate(tracks_to_download):
            if cancellation_check and cancellation_check():
                print("Загрузка обложек прервана.")
                break
            # Сообщаем о прогрессе скачивания обложек
            if progress_callback:
                progress_callback(i, total_to_download)

            filepath = os.path.join(self.covers_dir, f"{track['id']}.jpg")
            try:
                response = requests.get(track['cover_url'])
                response.raise_for_status()
                with open(filepath, 'wb') as f:
                    f.write(response.content)
                # Сразу обновляем наш кэш в памяти
                if track['id'] in self.track_cache:
                    self.track_cache[track['id']]['cover_path'] = filepath
            except requests.RequestException as e:
                print(f"Не удалось скачать обложку для {track['id']}: {e}")

    def _load_playlist_smart(self, playlist_id: str, cancellation_check=None, progress_callback=None, **kwargs) -> list[dict]:
        """
        Выполняет умную загрузку: проверяет кэш, загружает треки И, ЕСЛИ НУЖНО, их обложки.
        """
        current_snapshot_id = self.spotify_client.get_playlist_snapshot_id(
            playlist_id)
        cached_playlist = self.playlist_cache.get(playlist_id)

        # Сценарий А: КЭШ-ХИТ. Плейлист не менялся.
        if cached_playlist and cached_playlist.get('snapshot_id') == current_snapshot_id:
            print(f"КЭШ-ХИТ для плейлиста {playlist_id}.")
            track_ids = cached_playlist['track_ids']
            # Проверяем, нужно ли догрузить обложки для треков из кэша
            if self.window.show_covers_action.isChecked():
                tracks_to_check = [self.track_cache[tid]
                                   for tid in track_ids if tid in self.track_cache]
                self._download_covers_for_tracks(
                    tracks_to_check, cancellation_check, progress_callback)

            # Собираем финальный список из кэша ПОСЛЕ возможной дозагрузки обложек
            return [self.track_cache[tid] for tid in track_ids if tid in self.track_cache]

        # Сценарий Б: КЭШ-ПРОМАХ. Плейлист новый или был изменен.
        print(f"КЭШ-ПРОМАХ для плейлиста {playlist_id}.")

        # Шаг 1: Загружаем ID треков
        track_ids = self.spotify_client.get_playlist_track_ids(
            playlist_id, cancellation_check, progress_callback)
        if cancellation_check and cancellation_check():
            raise InterruptedError("Отменено.")

        # Шаг 2: Обновляем кэш плейлистов (L1)
        self.playlist_cache[playlist_id] = {
            "snapshot_id": current_snapshot_id, "track_ids": track_ids}

        # Шаг 3: Находим и загружаем детали для неизвестных треков
        new_track_ids = [
            tid for tid in track_ids if tid not in self.track_cache]
        if new_track_ids:
            new_track_details = self.spotify_client.get_tracks_details(
                new_track_ids)
            self.track_cache.update(new_track_details)

        # Шаг 4: Собираем предварительный список треков для проверки/загрузки обложек
        current_playlist_tracks = [self.track_cache[tid]
                                   for tid in track_ids if tid in self.track_cache]

        # Шаг 5: Если опция включена, скачиваем недостающие обложки
        if self.window.show_covers_action.isChecked():
            self.update_status("Загрузка обложек...", 0)
            self._download_covers_for_tracks(
                current_playlist_tracks, cancellation_check)

        # Шаг 6 (ФИНАЛ): Собираем итоговый список из кэша, который теперь точно содержит все данные
        return [self.track_cache[tid] for tid in track_ids if tid in self.track_cache]

    def refresh_track_view(self):
        """Запускает умную перезагрузку для текущего плейлиста."""
        if self.is_playlist_view and self.current_playlist_id:
            # Находим нужный item в списке и "кликаем" по нему программно
            items = self.window.playlist_list.findItems(
                self.current_playlist_name, Qt.MatchFlag.MatchExactly)
            if items:
                self.display_tracks_from_playlist(items[0])

    def search_and_display_tracks(self):
        """Инициирует фоновый поиск треков с использованием кэша."""
        if not self.spotify_client:
            return self.update_status("Сначала войдите в Spotify.")

        query = self.window.search_bar.text().strip()
        if not query:
            return

        self.is_playlist_view = False
        self.current_playlist_name = f"Результаты поиска по '{query}'"

        self.run_long_task(
            self._search_tracks_worker,
            self.on_tracks_loaded,  # Используем тот же обработчик, что и для плейлистов
            query,
            label_text=f"Поиск по запросу: '{query}'..."
        )

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
            # --> ИСПРАВЛЕНИЕ: Передаем target_id в лямбда-функцию <--
            lambda _: self.on_import_add_finished(
                len(found_ids), target_name, target_id),
            target_id,
            found_ids,
            label_text=f"Добавление треков в '{target_name}'..."
        )

    def on_import_add_finished(self, count, playlist_name, playlist_id):
        """Вызывается после завершения добавления треков в плейлист."""
        self.update_status(
            f"Успешно добавлено {count} треков в плейлист '{playlist_name}'.")

        # 1. Инвалидируем кэш для измененного плейлиста
        if playlist_id in self.playlist_cache:
            del self.playlist_cache[playlist_id]
            print(
                f"Кэш для плейлиста {playlist_id} инвалидирован после импорта.")

        # 2. Решаем, что обновить: текущий вид или общий список плейлистов
        if playlist_id == self.current_playlist_id:
            # Если мы смотрим на измененный плейлист, обновляем только его
            print("Обновление текущего вида плейлиста...")
            self.refresh_track_view()
        else:
            # Иначе, просто обновляем общий список плейлистов слева
            # (это важно, если был создан новый плейлист).
            print("Обновление общего списка плейлистов...")
            # Используем QTimer, чтобы избежать вложенных вызовов
            QTimer.singleShot(100, self.load_user_playlists)

    def confirm_and_delete_playlist(self, playlist_id, playlist_name):
        reply = QMessageBox.warning(self.window, "Подтверждение удаления",
                                    f"Вы уверены, что хотите удалить плейлист <br><b>{playlist_name}</b>?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.run_long_task(self.spotify_client.delete_playlist, self.on_playlist_deleted,
                               playlist_id, label_text=f"Удаление плейлиста '{playlist_name}'...")

    def remove_selected_from_playlist(self, track_ids):
        """Удаляет выделенные треки из текущего плейлиста."""
        playlist_id_to_modify = self.current_playlist_id
        self.run_long_task(
            self.spotify_client.remove_tracks_from_playlist,
            # --> ИЗМЕНЕНИЕ: Передаем ID и сообщение в обработчик <--
            lambda _: self.on_playlist_modified(
                playlist_id_to_modify, message="Треки удалены."),
            playlist_id_to_modify,
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
        и запускает синхронизацию, которая затем обновит вид, если нужно.
        """
        previously_selected_id = self.current_playlist_id
        self.playlists = playlists
        self.window.playlist_list.clear()

        newly_selected_item = None
        for playlist in self.playlists:
            item = QListWidgetItem(playlist['name'])
            self.window.playlist_list.addItem(item)
            if playlist['id'] == previously_selected_id:
                newly_selected_item = item

        if newly_selected_item:
            self.window.playlist_list.setCurrentItem(newly_selected_item)

        # Запускаем фоновый процесс синхронизации с новым обработчиком
        self.run_long_task(
            self._sync_cached_playlists_worker,
            self.on_sync_finished,  # <-- Используем новый обработчик
            playlists,
            label_text="Синхронизация кэша..."
        )

    def on_tracks_loaded(self, tracks):
        """
        Финальный слот: отображает треки и принудительно запускает загрузку обложек, если нужно.
        """
        if not isinstance(tracks, list):
            self.update_status(str(tracks))
            self.populate_track_table([])
            return

        # 1. Сразу отображаем текстовую информацию
        self.populate_track_table(tracks)
        self.update_status(f"Загружено {len(tracks)} треков.")

        # 2. ПРИНУДИТЕЛЬНЫЙ ЗАПУСК
        # Если опция уже была включена, имитируем ее повторное включение,
        # чтобы запустить гарантированно работающий процесс загрузки.
        if self.window.show_covers_action.isChecked():
            print("Принудительный запуск загрузки обложек для нового плейлиста...")
            # Используем таймер, чтобы этот вызов не конфликтовал с завершением текущего потока
            QTimer.singleShot(50, lambda: self.toggle_cover_visibility(True))

    def on_export_finished(self, success):
        self.update_status(
            "Экспорт успешно завершен." if success else "Ошибка во время экспорта.")

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

    def on_playlist_deleted(self, success):
        """Обработчик после удаления плейлиста. ИНВАЛИДИРУЕТ КЭШ."""
        # ID удаляемого плейлиста мы сохраняли в self.current_playlist_id
        playlist_id_to_invalidate = self.current_playlist_id
        if playlist_id_to_invalidate in self.playlist_cache:
            del self.playlist_cache[playlist_id_to_invalidate]
            print(
                f"Кэш для плейлиста {playlist_id_to_invalidate} инвалидирован.")

        if success:
            self.update_status("Плейлист успешно удален. Обновление списка...")
            QTimer.singleShot(100, self.load_user_playlists)
        else:
            self.update_status("Не удалось удалить плейлист.")

    def populate_track_table(self, tracks: list[dict]):
        """Очищает и заполняет таблицу треков, правильно масштабируя обложки."""
        self.window.track_table.blockSignals(True)
        self.window.track_table.setRowCount(0)
        self.window.track_table.setRowCount(len(tracks))

        show_covers = self.window.show_covers_action.isChecked()
        icon_size = self.window.track_table.iconSize()

        for row_num, track_data in enumerate(tracks):
            # Ячейка для обложки
            if show_covers:
                cover_item = QTableWidgetItem()
                self.window.track_table.setItem(row_num, 0, cover_item)

                cover_path = track_data.get('cover_path')
                if cover_path and os.path.exists(cover_path):
                    pixmap = QPixmap(cover_path)
                    # --> ГЛАВНОЕ ИЗМЕНЕНИЕ: Масштабируем с сохранением пропорций <--
                    scaled_pixmap = pixmap.scaled(
                        icon_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)

                    icon = QIcon(scaled_pixmap)
                    cover_item.setIcon(icon)

            # Остальные ячейки
            name_item = QTableWidgetItem(track_data['name'])
            name_item.setData(Qt.ItemDataRole.UserRole, track_data.get('id'))
            self.window.track_table.setItem(row_num, 1, name_item)
            self.window.track_table.setItem(
                row_num, 2, QTableWidgetItem(track_data['artist']))
            self.window.track_table.setItem(
                row_num, 3, QTableWidgetItem(track_data['album']))

        self.window.track_table.blockSignals(False)
        self.window.export_button.setEnabled(len(tracks) > 0)

    def toggle_cover_visibility(self, checked):
        """Обрабатывает включение/выключение обложек."""
        # Просто сохраняем настройку. Применение размера происходит при перезапуске
        self.settings['show_covers'] = checked
        self.window.track_table.setColumnHidden(0, not checked)
        if checked:
            self.run_long_task(self._download_covers_worker,
                               self.on_covers_downloaded, label_text="Загрузка обложек...")

    def _download_covers_worker(self, cancellation_check=None, progress_callback=None, **kwargs):
        """Рабочий метод: скачивает недостающие обложки для всех треков в кэше."""
        os.makedirs(self.covers_dir, exist_ok=True)

        tracks_to_download = [
            track for track in self.track_cache.values()
            if track.get('cover_url') and not track.get('cover_path')
        ]

        total_covers = len(tracks_to_download)
        for i, track in enumerate(tracks_to_download):
            if cancellation_check and cancellation_check():
                return "Загрузка отменена."
            if progress_callback:
                progress_callback(i, total_covers)

            filepath = os.path.join(self.covers_dir, f"{track['id']}.jpg")
            try:
                response = requests.get(track['cover_url'])
                response.raise_for_status()
                with open(filepath, 'wb') as f:
                    f.write(response.content)
                # Обновляем кэш, добавляя путь к скачанному файлу
                self.track_cache[track['id']]['cover_path'] = filepath
            except requests.RequestException as e:
                print(f"Не удалось скачать обложку для {track['id']}: {e}")

        return f"Загрузка обложек завершена. Скачано {total_covers} новых."

    def on_covers_downloaded(self, result_message):
        """
        Вызывается после завершения загрузки обложек.
        Напрямую обновляет таблицу, используя свежие данные из кэша.
        """
        self.update_status(result_message)

        # 1. Проверяем, включен ли еще режим показа обложек
        if not self.window.show_covers_action.isChecked():
            return

        # 2. Получаем ID текущего плейлиста, который мы просматриваем
        playlist_id = self.current_playlist_id
        if not playlist_id:
            return

        # 3. Получаем актуальный список ID треков для этого плейлиста из кэша
        cached_playlist = self.playlist_cache.get(playlist_id)
        if not cached_playlist:
            return  # На случай, если кэш был очищен

        track_ids = cached_playlist.get('track_ids', [])

        # 4. Получаем для них самые свежие данные из глобального кэша треков
        # (включая только что добавленные пути к обложкам)
        tracks_to_display = [self.track_cache[tid]
                             for tid in track_ids if tid in self.track_cache]

        # 5. Напрямую перерисовываем таблицу с этими данными
        print("Обновление таблицы для отображения скачанных обложек...")
        self.populate_track_table(tracks_to_display)

    def show_track_context_menu(self, position):
        selected_items = self.window.track_table.selectedItems()
        if not selected_items:
            return
        selected_track_ids = list(set(
            self.window.track_table.item(
                item.row(), 1).data(Qt.ItemDataRole.UserRole)
            for item in selected_items
        ))
        selected_track_ids = [tid for tid in selected_track_ids if tid]
        if not selected_track_ids:
            return
        menu = QMenu(self.window.track_table)
        add_to_playlist_menu = menu.addMenu("Добавить в плейлист")
        for playlist in self.playlists:
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

    def add_selected_to_playlist(self, playlist_id, track_ids):
        """Добавляет выделенные треки в плейлист."""
        if playlist_id == 'liked_songs':
            self.add_selected_to_liked(track_ids)
            return

        self.run_long_task(
            self.spotify_client.add_tracks_to_playlist,
            # --> ИЗМЕНЕНИЕ: Передаем ID и сообщение в обработчик <--
            lambda _: self.on_playlist_modified(
                playlist_id, message="Треки успешно добавлены."),
            playlist_id,
            track_ids,
            label_text="Добавление треков в плейлист..."
        )

    def on_playlist_modified(self, playlist_id_modified: str, result=None, message="Плейлист изменен. Обновление..."):
        """
        Универсальный обработчик, который вызывается после любого изменения плейлиста.
        """
        # 1. Инвалидируем кэш для того плейлиста, который был изменен
        if playlist_id_modified in self.playlist_cache:
            del self.playlist_cache[playlist_id_modified]
            print(f"Кэш для плейлиста {playlist_id_modified} инвалидирован.")

        # 2. Формируем и показываем сообщение в строке состояния
        status_message = message
        if isinstance(result, int):  # Для удаления дубликатов
            status_message = f"Удалено {result} дубликатов. Обновление..."
        self.update_status(status_message)

        # 3. Если измененный плейлист сейчас на экране - обновляем вид
        if playlist_id_modified == self.current_playlist_id:
            self.refresh_track_view()

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

        # --> ИСПРАВЛЕНИЕ: Вызываем новый правильный метод <--
        track_ids = self.spotify_client.get_playlist_track_ids(
            playlist_id, cancellation_check, progress_callback)

        if cancellation_check and cancellation_check():
            raise InterruptedError("Операция отменена.")

        # Теперь нам не нужно извлекать ID, мы их уже получили
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
            self.run_long_task(
                self.spotify_client.deduplicate_playlist,
                # --> ИЗМЕНЕНИЕ: Передаем ID и результат в обработчик <--
                lambda res: self.on_playlist_modified(playlist_id, result=res),
                playlist_id,
                label_text="Удаление дубликатов..."
            )


if __name__ == '__main__':
    os.makedirs('data', exist_ok=True)
    os.makedirs('.app_cache', exist_ok=True)

    app = QApplication(sys.argv)

    try:
        with open("style.qss", "r") as f:
            app.setStyleSheet(f.read())
    except FileNotFoundError:
        print("Файл style.qss не найден. Будет использован стандартный стиль.")

    spotify_app = SpotifyApp()

    # --> НОВОЕ: Подключаем сохранение кэша к сигналу о выходе <--
    app.aboutToQuit.connect(spotify_app.save_cache)
    app.aboutToQuit.connect(spotify_app.save_settings)

    if spotify_app.auth_manager.get_cached_token():
        print("Обнаружен кешированный токен, автоматический вход...")
        spotify_app.on_login_success()

    spotify_app.window.show()
    sys.exit(app.exec())
