# ai_assistant.py

import os
import re
import google.generativeai as genai


class AIAssistant:
    """
    Класс-ассистент для генерации рекомендаций с помощью Google Gemini.
    """

    def __init__(self, api_key: str):
        """
        Инициализирует модель Gemini, используя переданный ключ API.
        """
        self.model = None
        self.is_active = False
        try:
            if not api_key:
                raise ValueError("API ключ не предоставлен.")

            genai.configure(api_key=api_key)
            self.is_active = True
            print("AI-ассистент успешно настроен.")
        except Exception as e:
            print(f"Ошибка конфигурации AI-ассистента: {e}")
            # Возвращаем ошибку, чтобы основной код мог ее обработать
            raise

    def _generate(self, prompt: str, model_name: str = 'gemini-pro'):
        """Общий метод для отправки запроса к указанной модели."""
        if not self.is_active:
            raise ConnectionError("AI-ассистент не был инициализирован.")

        try:
            model = genai.GenerativeModel(model_name)
            print(f"Отправка запроса в модель {model_name}...")
            response = model.generate_content(prompt)
            return [line.strip() for line in response.text.split('\n') if line.strip()]
        except Exception as e:
            print(f"Ошибка при обращении к Gemini API: {e}")
            # Пробрасываем ошибку дальше, чтобы ее можно было показать пользователю
            raise

    def get_recommendations_from_prompt(self, user_prompt: str, model_name: str, num_tracks: int = 15) -> list[str]:
        """Генерирует список треков на основе текстового запроса пользователя."""
        full_prompt = (
            "Ты — музыкальный эксперт и диджей. На основе запроса пользователя "
            f"порекомендуй ему список из {num_tracks} треков. "
            "Ответ должен быть простым списком, где каждая строка имеет формат 'Исполнитель - Название'. "
            "Не добавляй нумерацию, заголовки или любые другие пояснения. Просто список.\n\n"
            f"Запрос пользователя: \"{user_prompt}\""
        )
        return self._generate(full_prompt, model_name)

    def get_recommendations_from_playlist(self, existing_tracks: list[dict], model_name: str, num_tracks: int = 15) -> list[str]:
        """Генерирует список треков, анализируя существующий плейлист."""
        track_list_str = "\n".join(
            [f"{track['artist']} - {track['name']}" for track in existing_tracks])

        full_prompt = (
            "Ты — музыкальный рекомендательный движок. Я предоставлю тебе список треков из плейлиста. "
            f"Проанализируй их и предложи {num_tracks} НОВЫХ, ДРУГИХ треков, которые хорошо впишутся в этот плейлист. "
            "Не включай в ответ песни из предоставленного списка. "
            "Ответ должен быть простым списком в формате 'Исполнитель - Название'. "
            "Не добавляй нумерацию, заголовки или пояснения.\n\n"
            "Вот треки из плейлиста:\n"
            f"{track_list_str}"
        )
        return self._generate(full_prompt, model_name)

    # ai_assistant.py, внутри класса AIAssistant

    def list_supported_models(self, show_all: bool = False, **kwargs) -> list[str]:
        """
        Получает список моделей и фильтрует его, если не включен режим show_all.
        """
        if not self.is_active:
            raise ConnectionError("AI-ассистент не был инициализирован.")

        print(f"Запрос списка AI моделей (Показать все: {show_all})...")

        # Ключевые слова для исключения в стандартном режиме
        EXCLUDE_KEYWORDS = {'vision', 'preview', 'exp',
                            'lite', 'tts', 'thinking', 'code', 'gemma'}

        all_models = []
        try:
            # Сначала получаем абсолютно все поддерживаемые модели
            for m in genai.list_models():
                if 'generateContent' in m.supported_generation_methods:
                    all_models.append(m.name.split('/')[-1])

            # Если не стоит флаг "показать все", применяем наш умный фильтр
            if not show_all:
                filtered_models = []
                for model_name in all_models:
                    if any(keyword in model_name for keyword in EXCLUDE_KEYWORDS):
                        continue
                    is_numbered_version = model_name[-4:].startswith(
                        '-') and model_name[-3:].isdigit()
                    if is_numbered_version:
                        continue
                    filtered_models.append(model_name)
                main_models = filtered_models
            else:
                main_models = all_models

            # Сортируем итоговый список
            def sort_key(name):
                # ... (логика сортировки остается без изменений) ...
                family_prio = 0 if 'gemini' in name else (
                    1 if 'gemma' in name else 2)
                tier_prio = 0 if 'pro' in name else (
                    1 if 'flash' in name else 2)
                latest_prio = 0 if 'latest' in name else 1
                version_match = re.search(r'(\d\.\d|\d)', name)
                version = float(version_match.group(1)) if version_match else 0
                return (family_prio, -version, tier_prio, latest_prio)

            main_models.sort(key=sort_key)

            print(f"Итоговый список моделей для отображения: {main_models}")
            return main_models
        except Exception as e:
            print(f"Не удалось получить список моделей: {e}")
            return ['gemini-2.5-flash']
