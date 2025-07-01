import spotipy
from itertools import islice


def chunks(iterable, size=100):
    iterator = iter(iterable)
    while chunk := list(islice(iterator, size)):
        yield chunk


class SpotifyClient:
    def __init__(self, spotipy_oauth_manager):
        self.sp = spotipy.Spotify(
            auth_manager=spotipy_oauth_manager, requests_timeout=None)

    def _get_all_items(self, results, cancellation_check=None, progress_callback=None):
        """Собирает все элементы со всех страниц, сообщая о прогрессе."""
        total = results.get('total', 0)
        items = results.get('items', [])
        if progress_callback:
            progress_callback(len(items), total)

        while results and results.get('next'):
            if cancellation_check and cancellation_check():
                print("Загрузка страниц прервана.")
                break
            results = self.sp.next(results)
            if results:
                new_items = results.get('items', [])
                items.extend(new_items)
                if progress_callback:
                    # Сообщаем о новом количестве загруженных
                    progress_callback(len(items), total)
        return items

    def get_user_playlists(self, cancellation_check=None, progress_callback=None, **kwargs) -> list[dict]:
        playlists_data = [{'id': 'liked_songs',
                           'name': 'Понравившиеся треки (Liked Songs)'}]
        results = self.sp.current_user_playlists()
        all_playlist_items = self._get_all_items(
            results, cancellation_check, progress_callback)
        for item in all_playlist_items:
            playlists_data.append({'id': item['id'], 'name': item['name']})
        return playlists_data

    def get_playlist_tracks(self, playlist_id: str, cancellation_check=None, progress_callback=None, **kwargs) -> list[dict]:
        if playlist_id == 'liked_songs':
            results = self.sp.current_user_saved_tracks(limit=50)
        else:
            results = self.sp.playlist_tracks(playlist_id, limit=50)
        all_track_items = self._get_all_items(
            results, cancellation_check, progress_callback)
        if not all_track_items:
            return []
        # _parse_tracks быстрый, ему прогресс не нужен
        return self._parse_tracks(all_track_items)

    def search_tracks(self, query: str, limit: int = 50, cancellation_check=None, progress_callback=None, **kwargs) -> list[dict]:
        if not query:
            return []
        results = self.sp.search(q=query, type='track', limit=limit)
        track_items = results.get('tracks', {}).get('items', [])
        if not track_items:
            return []
        return self._parse_tracks(track_items)

    def _parse_tracks(self, track_items: list[dict], **kwargs) -> list[dict]:
        tracks_data = []
        for item in track_items:
            track = item.get('track') or item
            if not track or not track.get('id'):
                continue
            artists = ', '.join(artist['name'] for artist in track['artists'])
            album_name = track.get('album', {}).get('name', 'N/A')
            tracks_data.append(
                {'id': track['id'], 'name': track['name'], 'artist': artists, 'album': album_name})
        return tracks_data

    def add_tracks_to_playlist(self, playlist_id: str, track_ids: list[str], **kwargs):
        return self.sp.playlist_add_items(playlist_id, track_ids)

    def remove_tracks_from_playlist(self, playlist_id: str, track_ids: list[str], **kwargs):
        track_uris = [f"spotify:track:{track_id}" for track_id in track_ids]
        return self.sp.playlist_remove_all_occurrences_of_items(playlist_id, track_uris)

    def check_if_tracks_are_liked(self, track_ids: list[str], **kwargs) -> list[bool]:
        return self.sp.current_user_saved_tracks_contains(track_ids)

    def add_tracks_to_liked(self, track_ids: list[str], **kwargs):
        return self.sp.current_user_saved_tracks_add(track_ids)

    def remove_tracks_from_liked(self, track_ids: list[str], **kwargs):
        return self.sp.current_user_saved_tracks_delete(track_ids)

    def delete_playlist(self, playlist_id: str, **kwargs):
        self.sp.current_user_unfollow_playlist(playlist_id)
        return True

    def find_track_id(self, query: str, **kwargs) -> str | None:
        try:
            results = self.sp.search(q=query, type='track', limit=1)
            items = results.get('tracks', {}).get('items', [])
            if items:
                return items[0]['id']
        except Exception as e:
            print(f"Ошибка при поиске трека '{query}': {e}")
        return None

    def create_new_playlist(self, name: str, **kwargs) -> str | None:
        try:
            user_id = self.sp.me()['id']
            playlist = self.sp.user_playlist_create(
                user=user_id, name=name, public=False)
            return playlist['id']
        except Exception as e:
            print(f"Ошибка при создании плейлиста '{name}': {e}")
        return None
