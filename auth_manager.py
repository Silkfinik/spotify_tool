# Модуль для управления авторизацией Spotify

import os
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv

CACHE_FILE = ".spotify_cache"


class AuthManager:
    """
    Управляет процессом аутентификации Spotify с использованием Authorization Code Flow.
    """

    def __init__(self):
        """
        Инициализирует AuthManager, загружая учетные данные из переменных окружения.
        """
        load_dotenv()

        self.client_id = os.getenv("SPOTIPY_CLIENT_ID")
        self.client_secret = os.getenv("SPOTIPY_CLIENT_SECRET")
        self.redirect_uri = os.getenv("SPOTIPY_REDIRECT_URI")

        if not all([self.client_id, self.client_secret, self.redirect_uri]):
            raise ValueError("Ошибка: Установите переменные окружения SPOTIPY_CLIENT_ID, "
                             "SPOTIPY_CLIENT_SECRET, и SPOTIPY_REDIRECT_URI в файле .env")

        # auth_manager.py, внутри __init__
        scope = "user-read-private user-read-email playlist-read-private user-library-read"

        self.sp_oauth = SpotifyOAuth(
            client_id=self.client_id,
            client_secret=self.client_secret,
            redirect_uri=self.redirect_uri,
            scope=scope,
            cache_path=CACHE_FILE
        )

    def get_auth_url(self) -> str:
        """
        Возвращает URL-адрес, на который пользователь должен перейти для авторизации.

        Returns:
            str: URL для авторизации Spotify.
        """
        return self.sp_oauth.get_authorize_url()

    def get_token(self, code: str) -> dict:
        """
        Обменивает авторизационный код на токен доступа и сохраняет его в кеш.

        Args:
            code (str): Код, полученный от Spotify после редиректа.

        Returns:
            dict: Информация о токене.
        """
        token_info = self.sp_oauth.get_access_token(code, as_dict=True)
        return token_info

    def get_cached_token(self) -> dict | None:
        """
        Загружает информацию о токене из кеша, если он существует.

        Returns:
            dict | None: Информация о токене или None, если кеш пуст.
        """
        return self.sp_oauth.get_cached_token()

    def create_spotify_client(self) -> spotipy.Spotify | None:
        """
        Создает аутентифицированный клиент spotipy.Spotify.

        Пытается использовать кешированный токен. Если токена нет, возвращает None.
        Этот клиент будет автоматически обновлять токен при истечении его срока действия.

        Returns:
            spotipy.Spotify | None: Аутентифицированный объект Spotify или None.
        """
        token_info = self.get_cached_token()

        if not token_info:
            print("Токен не найден в кеше. Необходимо пройти аутентификацию.")
            return None

        return spotipy.Spotify(auth_manager=self.sp_oauth)
