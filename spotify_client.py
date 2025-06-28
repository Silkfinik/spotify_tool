# spotify_client.py

import spotipy


class SpotifyClient:
    """
    Клиент для работы с данными Spotify.
    """

    def __init__(self, spotipy_oauth_manager):
        self.sp = spotipy.Spotify(
            auth_manager=spotipy_oauth_manager,
            requests_timeout=None
        )

    def _get_all_items(self, results):
        """Собирает все элементы со всех страниц ответа API."""
        items = results.get('items', [])
        while results and results.get('next'):
            results = self.sp.next(results)
            items.extend(results.get('items', []))
        return items

    def get_user_playlists(self) -> list[dict]:
        """Возвращает список плейлистов пользователя, включая "Понравившиеся треки"."""
        playlists_data = [{'id': 'liked_songs',
                           'name': 'Понравившиеся треки (Liked Songs)'}]
        results = self.sp.current_user_playlists()
        all_playlist_items = self._get_all_items(results)
        for item in all_playlist_items:
            playlists_data.append({'id': item['id'], 'name': item['name']})
        return playlists_data

    def get_playlist_tracks(self, playlist_id: str) -> list[dict]:
        """Возвращает треки для плейлиста или 'Понравившихся треков'."""
        if playlist_id == 'liked_songs':
            results = self.sp.current_user_saved_tracks(limit=50)
        else:
            results = self.sp.playlist_tracks(playlist_id, limit=50)

        all_track_items = self._get_all_items(results)
        return self._parse_tracks(all_track_items)

    def search_tracks(self, query: str, limit: int = 50) -> list[dict]:
        """Ищет треки на Spotify."""
        if not query:
            return []
        results = self.sp.search(q=query, type='track', limit=limit)
        track_items = results.get('tracks', {}).get('items', [])
        if not track_items:
            return []
        # --> ИСПРАВЛЕНИЕ ЗДЕСЬ <--
        return self._parse_tracks(track_items)

    def _parse_tracks(self, track_items: list[dict]) -> list[dict]:
        """Просто извлекает базовые данные о треках."""
        tracks_data = []
        for item in track_items:
            track = item.get('track') or item
            if not track or not track.get('id'):
                continue

            artists = ', '.join(artist['name'] for artist in track['artists'])
            album_name = track.get('album', {}).get('name', 'N/A')
            tracks_data.append({
                'id': track['id'],
                'name': track['name'],
                'artist': artists,
                'album': album_name
            })
        return tracks_data

    # Тут должны быть только базовые методы управления, без аудио-фич
    def add_tracks_to_playlist(self, playlist_id: str, track_ids: list[str]):
        return self.sp.playlist_add_items(playlist_id, track_ids)

    def remove_tracks_from_playlist(self, playlist_id: str, track_ids: list[str]):
        track_uris = [f"spotify:track:{track_id}" for track_id in track_ids]
        return self.sp.playlist_remove_all_occurrences_of_items(playlist_id, track_uris)

    def check_if_tracks_are_liked(self, track_ids: list[str]) -> list[bool]:
        return self.sp.current_user_saved_tracks_contains(track_ids)

    def add_tracks_to_liked(self, track_ids: list[str]):
        return self.sp.current_user_saved_tracks_add(track_ids)

    def remove_tracks_from_liked(self, track_ids: list[str]):
        return self.sp.current_user_saved_tracks_delete(track_ids)

    def find_track_id(self, query: str) -> str | None:
        """
        Ищет один трек и возвращает его ID.

        Args:
            query (str): Поисковый запрос (например, "Artist - Track Name").

        Returns:
            str | None: Spotify ID первого найденного трека или None.
        """
        try:
            results = self.sp.search(q=query, type='track', limit=1)
            items = results.get('tracks', {}).get('items', [])
            if items:
                return items[0]['id']
        except Exception as e:
            print(f"Ошибка при поиске трека '{query}': {e}")
        return None

    def create_new_playlist(self, name: str) -> str | None:
        """
        Создает новый приватный плейлист для текущего пользователя.

        Args:
            name (str): Название нового плейлиста.

        Returns:
            str | None: ID нового плейлиста или None в случае ошибки.
        """
        try:
            user_id = self.sp.me()['id']
            playlist = self.sp.user_playlist_create(
                user=user_id, name=name, public=False)
            return playlist['id']
        except Exception as e:
            print(f"Ошибка при создании плейлиста '{name}': {e}")
        return None

    def delete_playlist(self, playlist_id: str):
        """Отписывается от плейлиста (удаляет его из медиатеки пользователя)."""
        self.sp.current_user_unfollow_playlist(playlist_id)  # <-- ИСПРАВЛЕНО
        # Этот метод не возвращает ничего, поэтому мы можем вернуть True в случае успеха
        return True
