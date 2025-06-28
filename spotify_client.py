# spotify_client.py

import spotipy


class SpotifyClient:
    """
    Клиент для работы с данными Spotify.
    """

    def __init__(self, spotipy_oauth_manager):
        self.sp = spotipy.Spotify(auth_manager=spotipy_oauth_manager)

    def get_user_playlists(self) -> list[dict]:
        # ... код без изменений ...
        playlists_data = []
        liked_songs_playlist = {
            'id': 'liked_songs',
            'name': 'Понравившиеся треки (Liked Songs)'
        }
        playlists_data.append(liked_songs_playlist)
        results = self.sp.current_user_playlists()
        while results:
            for item in results['items']:
                playlists_data.append({'id': item['id'], 'name': item['name']})
            if results['next']:
                results = self.sp.next(results)
            else:
                results = None
        return playlists_data

    def get_playlist_tracks(self, playlist_id: str) -> list[dict]:
        if playlist_id == 'liked_songs':
            results = self.sp.current_user_saved_tracks()
        else:
            results = self.sp.playlist_tracks(playlist_id)
        return self._parse_tracks(results)

    # --> НОВЫЙ МЕТОД <--
    def search_tracks(self, query: str, limit: int = 50) -> list[dict]:
        """
        Ищет треки на Spotify по заданному запросу.

        Args:
            query (str): Строка для поиска.
            limit (int): Максимальное количество результатов.

        Returns:
            list[dict]: Список найденных треков.
        """
        if not query:
            return []

        # Метод search возвращает словарь, где результаты находятся в ключе 'tracks'
        results = self.sp.search(q=query, type='track', limit=limit)
        return self._parse_tracks(results['tracks'])

    def _parse_tracks(self, results: dict) -> list[dict]:
        # ... код без изменений ...
        tracks_data = []
        while results:
            for item in results['items']:
                track = item.get('track')
                if not track:
                    # Для результатов поиска, 'track' может отсутствовать,
                    # сам 'item' является треком.
                    track = item

                artists = ', '.join(artist['name']
                                    for artist in track['artists'])

                # Некоторые треки могут быть без альбома (например, подкасты)
                album_name = track.get('album', {}).get('name', 'N/A')

                tracks_data.append({
                    'name': track['name'],
                    'artist': artists,
                    'album': album_name
                })

            # Логика пагинации для поиска отличается, пока оставим только первую страницу
            # if results.get('next'):
            #     results = self.sp.next(results)
            # else:
            results = None

        return tracks_data

    def add_tracks_to_playlist(self, playlist_id: str, track_ids: list[str]):
        """Добавляет треки в указанный плейлист."""
        return self.sp.playlist_add_items(playlist_id, track_ids)

    def remove_tracks_from_playlist(self, playlist_id: str, track_ids: list[str]):
        """Удаляет треки из указанного плейлиста."""
        # Этот метод требует URI треков, а не просто ID
        track_uris = [f"spotify:track:{track_id}" for track_id in track_ids]
        return self.sp.playlist_remove_all_occurrences_of_items(playlist_id, track_uris)

    def check_if_tracks_are_liked(self, track_ids: list[str]) -> list[bool]:
        """Проверяет, находятся ли треки в 'Понравившихся'."""
        return self.sp.current_user_saved_tracks_contains(track_ids)

    def add_tracks_to_liked(self, track_ids: list[str]):
        """Добавляет треки в 'Понравившиеся'."""
        return self.sp.current_user_saved_tracks_add(track_ids)

    def remove_tracks_from_liked(self, track_ids: list[str]):
        """Удаляет треки из 'Понравившихся'."""
        return self.sp.current_user_saved_tracks_delete(track_ids)
