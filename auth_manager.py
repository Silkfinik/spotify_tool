# auth_manager.py

import spotipy
from spotipy.oauth2 import SpotifyOAuth

# ВАЖНО: Вставьте сюда ВАШ Client ID. Он не является секретом.
CLIENT_ID = "3bed272eca794a1e96f19a97e9a5a38e"

# Этот URI должен в точности совпадать с тем, что указан в настройках
# вашего приложения на Spotify Developer Dashboard.
REDIRECT_URI = "http://127.0.0.1:8888/callback"

CACHE_FILE = ".spotify_cache"


class AuthManager:
    """
    Управляет процессом аутентификации Spotify с использованием
    безопасного потока PKCE, не требующего Client Secret.
    """

    def __init__(self):
        if not CLIENT_ID or CLIENT_ID == "СЮДА_ВСТАВЬТЕ_ВАШ_CLIENT_ID":
            raise ValueError(
                "Ошибка: Client ID не указан в файле auth_manager.py")

        # Определяем все права, которые нужны нашему приложению
        scope = (
            "user-read-private user-read-email "
            "playlist-read-private "
            "playlist-modify-public playlist-modify-private "
            "user-library-read user-library-modify"
        )

        # Создаем объект SpotifyOAuth, НЕ ПЕРЕДАВАЯ client_secret.
        # spotipy автоматически переключится на безопасный PKCE-поток.
        self.sp_oauth = SpotifyOAuth(
            client_id=CLIENT_ID,
            redirect_uri=REDIRECT_URI,
            scope=scope,
            cache_path=CACHE_FILE
        )

    def get_auth_url(self) -> str:
        return self.sp_oauth.get_authorize_url()

    def get_token(self, code: str) -> dict:
        token_info = self.sp_oauth.get_access_token(code, as_dict=True)
        return token_info

    def get_cached_token(self) -> dict | None:
        return self.sp_oauth.get_cached_token()
