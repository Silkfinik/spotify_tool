# spotify_client.py

import spotipy
from itertools import islice


def chunks(iterable, size=50):
    """Разбивает итерируемый объект на части заданного размера."""
    iterator = iter(iterable)
    while chunk := list(islice(iterator, size)):
        yield chunk


class SpotifyClient:
    def __init__(self, spotipy_oauth_manager):
        self.sp = spotipy.Spotify(
            auth_manager=spotipy_oauth_manager,
            requests_timeout=10
        )

    def get_user_playlists(self, cancellation_check=None, progress_callback=None, **kwargs) -> list[dict]:
        """Возвращает список плейлистов пользователя, включая "Понравившиеся треки"."""
        # Начинаем со статичного плейлиста "Понравившиеся"
        playlists_data = [{'id': 'liked_songs',
                           'name': 'Понравившиеся треки (Liked Songs)'}]

        # Запрашиваем плейлисты пользователя
        results = self.sp.current_user_playlists()

        # Собираем плейлисты со всех страниц ответа
        all_playlist_items = self._get_all_items(
            results, cancellation_check, progress_callback)

        for item in all_playlist_items:
            if item:  # Дополнительная проверка на пустые элементы
                playlists_data.append({'id': item['id'], 'name': item['name']})

        return playlists_data

    def get_playlist_snapshot_id(self, playlist_id: str, **kwargs) -> str | None:
        """Легковесный запрос для получения только snapshot_id плейлиста."""
        if playlist_id == 'liked_songs':
            # У "Понравившихся" нет snapshot_id, но мы можем использовать
            # общее количество треков и дату добавления последнего как своего рода "хэш"
            results = self.sp.current_user_saved_tracks(limit=1)
            if results['items']:
                return f"{results['total']}-{results['items'][0]['added_at']}"
            return "no-items"

        try:
            # Запрашиваем только одно поле для максимальной скорости
            return self.sp.playlist(playlist_id, fields='snapshot_id').get('snapshot_id')
        except Exception:
            return None

    def get_playlist_track_ids(self, playlist_id: str, cancellation_check=None, progress_callback=None) -> list[str]:
        """Загружает ПОЛНЫЙ список ID треков из плейлиста или 'Понравившихся'."""
        if playlist_id == 'liked_songs':
            results = self.sp.current_user_saved_tracks(limit=50)
        else:
            results = self.sp.playlist_tracks(
                playlist_id, fields='items(track(id,type,is_local)),next,total', limit=50)

        all_items = self._get_all_items(
            results, cancellation_check, progress_callback)

        track_ids = []
        for item in all_items:
            track = item.get('track') or item
            if track and track.get('type') == 'track' and not track.get('is_local') and track.get('id'):
                track_ids.append(track['id'])
        return track_ids

    def get_tracks_details(self, track_ids: list[str]) -> dict:
        """
        Принимает список ID треков и возвращает словарь с их базовой информацией,
        ВКЛЮЧАЯ URL на обложку альбома.
        """
        if not track_ids:
            return {}

        tracks_details_dict = {}

        # Запрашиваем информацию о треках пакетами по 50
        for id_chunk in chunks(track_ids, 50):
            try:
                tracks_info = self.sp.tracks(id_chunk)
                for track in tracks_info['tracks']:
                    if not track:
                        continue

                    # --> ВОЗВРАЩАЕМ ЛОГИКУ ПОИСКА URL ОБЛОЖКИ <--
                    cover_url = None
                    if track.get('album') and track['album'].get('images'):
                        # Берем последнюю картинку в списке, она самая маленькая (64x64)
                        cover_url = track['album']['images'][-1]['url']

                    # Собираем полную информацию о треке
                    tracks_details_dict[track['id']] = {
                        'id': track['id'],
                        'name': track['name'],
                        'artist': ', '.join(artist['name'] for artist in track['artists']),
                        'album': track.get('album', {}).get('name', 'N/A'),
                        'cover_url': cover_url  # Добавляем URL в данные кэша
                    }
            except Exception as e:
                print(f"Ошибка при получении информации о треках: {e}")

        return tracks_details_dict

    def _get_all_items(self, results, cancellation_check=None, progress_callback=None):
        """Собирает все элементы со всех страниц ответа API, сообщая о прогрессе."""
        total = results.get('total', 0)
        items = results.get('items', [])
        if progress_callback and total > 0:
            progress_callback(len(items), total)

        while results and results.get('next'):
            if cancellation_check and cancellation_check():
                print("Загрузка страниц прервана.")
                break
            try:
                results = self.sp.next(results)
                if results:
                    new_items = results.get('items', [])
                    items.extend(new_items)
                    if progress_callback and total > 0:
                        progress_callback(len(items), total)
            except Exception as e:
                print(f"Ошибка при загрузке следующей страницы: {e}")
                break
        return items

    # --- Методы, которые мы пока не трогаем, но они должны принимать **kwargs ---
    def search_tracks(self, query: str, limit: int = 50, **kwargs) -> list[str]:
        """
        Ищет треки на Spotify и возвращает список их ID.
        """
        if not query:
            return []

        try:
            results = self.sp.search(q=query, type='track', limit=limit)
            track_items = results.get('tracks', {}).get('items', [])

            # Собираем ID только валидных треков (не локальных, не подкастов)
            track_ids = [
                track['id'] for track in track_items
                if track and track.get('type') == 'track' and not track.get('is_local') and track.get('id')
            ]
            return track_ids
        except Exception as e:
            print(f"Ошибка при поиске по запросу '{query}': {e}")
            return []

    def find_track_id(self, query: str, **kwargs) -> str | None:
        try:
            results = self.sp.search(q=query, type='track', limit=1)
            items = results.get('tracks', {}).get('items', [])
            if items:
                return items[0].get('id')
        except Exception as e:
            print(f"Ошибка при поиске трека '{query}': {e}")
        return None

    # --- Методы для управления плейлистами ---
    def create_new_playlist(self, name: str, **kwargs) -> str | None:
        try:
            user_id = self.sp.me()['id']
            playlist = self.sp.user_playlist_create(
                user=user_id, name=name, public=False)
            return playlist.get('id')
        except Exception as e:
            print(f"Ошибка при создании плейлиста '{name}': {e}")
        return None

    def add_tracks_to_playlist(self, playlist_id: str, track_ids: list[str], **kwargs):
        return self.sp.playlist_add_items(playlist_id, track_ids)

    def deduplicate_playlist(self, playlist_id: str, cancellation_check=None, progress_callback=None, **kwargs):
        """
        Удаляет дубликаты из плейлиста, заменяя его содержимое на уникальный список треков.
        """
        try:
            print("\n--- ЗАПУСК УДАЛЕНИЯ ДУБЛИКАТОВ ---")

            # --> ИСПРАВЛЕНИЕ: Вызываем get_playlist_track_ids для получения только ID <--
            all_track_ids = self.get_playlist_track_ids(
                playlist_id, cancellation_check, progress_callback)
            if cancellation_check and cancellation_check():
                raise InterruptedError("Операция отменена.")

            print(
                f"DEBUG: Шаг 1: Всего загружено {len(all_track_ids)} треков из плейлиста.")

            # 2. Собираем уникальные ID в порядке их первого появления
            seen_ids = set()
            unique_track_ids = []
            for track_id in all_track_ids:
                if track_id not in seen_ids:
                    unique_track_ids.append(track_id)
                    seen_ids.add(track_id)

            num_duplicates = len(all_track_ids) - len(unique_track_ids)
            print(
                f"DEBUG: Шаг 2: Найдено {len(unique_track_ids)} уникальных треков. Количество дубликатов: {num_duplicates}.")

            if num_duplicates == 0:
                print("DEBUG: Дубликаты не найдены, операция завершена.")
                return 0

            # 3. Полностью заменяем треки в плейлисте на уникальный список
            print(
                f"DEBUG: Шаг 3: Вызываю playlist_replace_items с {len(unique_track_ids)} уникальными ID...")
            self.sp.playlist_replace_items(playlist_id, unique_track_ids)

            print("DEBUG: Шаг 4: Вызов API успешно завершен.")
            print("--- УДАЛЕНИЕ ДУБЛИКАТОВ ЗАВЕРШЕНО ---\n")

            return num_duplicates

        except Exception as e:
            print(
                f"---!!! КРИТИЧЕСКАЯ ОШИБКА в deduplicate_playlist: {e} !!!---")
            raise

    def check_if_tracks_are_liked(self, track_ids: list[str], **kwargs) -> list[bool]:
        """Проверяет, находятся ли треки в 'Понравившихся'."""
        return self.sp.current_user_saved_tracks_contains(track_ids)

    def add_tracks_to_liked(self, track_ids: list[str], **kwargs):
        """Добавляет треки в 'Понравившиеся'."""
        return self.sp.current_user_saved_tracks_add(track_ids)

    def remove_tracks_from_liked(self, track_ids: list[str], **kwargs):
        """Удаляет треки из 'Понравившихся'."""
        return self.sp.current_user_saved_tracks_delete(track_ids)

    def delete_playlist(self, playlist_id: str, **kwargs):
        self.sp.current_user_unfollow_playlist(playlist_id)
        return True

    def remove_tracks_from_playlist(self, playlist_id: str, track_ids: list[str], **kwargs):
        """Удаляет все вхождения указанных треков из плейлиста."""
        # Этот метод spotipy требует URI треков, а не просто ID.
        track_uris = [f"spotify:track:{track_id}" for track_id in track_ids]
        self.sp.playlist_remove_all_occurrences_of_items(
            playlist_id, track_uris)
        return True
