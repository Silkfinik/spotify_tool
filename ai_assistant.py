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
        if not self.is_active:
            raise ConnectionError("AI-ассистент не был инициализирован.")
        try:
            model = genai.GenerativeModel(model_name)
            print(f"Отправка запроса в модель {model_name}...")
            response = model.generate_content(prompt)
            return [line.strip() for line in response.text.split('\n') if line.strip()]
        except Exception as e:
            print(f"Ошибка при обращении к Gemini API: {e}")
            raise

    def get_recommendations_from_prompt(self, user_prompt: str, model_name: str, num_tracks: int) -> list[str]:
        full_prompt = (
            "Ты — музыкальный эксперт. На основе запроса пользователя "
            f"порекомендуй ему список из {num_tracks} треков. "
            "Ответ должен быть простым списком в формате 'Исполнитель - Название'. "
            "Не добавляй нумерацию или заголовки.\n\n"
            f"Запрос пользователя: \"{user_prompt}\""
        )
        return self._generate(full_prompt, model_name)

    def get_recommendations_from_playlist(self, existing_tracks: list[dict], model_name: str, num_tracks: int, refining_prompt: str = "") -> list[str]:
        track_list_str = "\n".join(
            [f"{track['artist']} - {track['name']}" for track in existing_tracks])

        # --> ИЗМЕНЕНИЕ: Добавляем уточняющий промпт, если он есть <--
        refining_text = ""
        if refining_prompt:
            refining_text = f"Дополнительное пожелание от пользователя: \"{refining_prompt}\". Учти его при генерации."

        full_prompt = (
            "Ты — музыкальный рекомендательный движок. Я предоставлю тебе список треков из плейлиста. "
            "Проанализируй их жанр, настроение и стиль. "
            f"На основе этого анализа, предложи мне {num_tracks} НОВЫХ треков, которые хорошо впишутся в плейлист. "
            f"{refining_text} "  # Вставляем уточнение
            "Не включай в ответ песни из предоставленного списка. "
            "Ответ должен быть простым списком в формате 'Исполнитель - Название'. "
            "Не добавляй нумерацию или заголовки.\n\n"
            "Вот треки из плейлиста:\n"
            f"{track_list_str}"
        )
        return self._generate(full_prompt, model_name)

    # ai_assistant.py, внутри класса AIAssistant

    def list_supported_models(self, show_all: bool = False, **kwargs) -> list[str]:
        """
        Получает список моделей и фильтрует его.
        В случае ошибки API, выбрасывает исключение.
        """
        if not self.is_active:
            raise ConnectionError("AI-ассистент не был инициализирован.")

        print(f"Запрос списка AI моделей (Показать все: {show_all})...")

        # --> УБИРАЕМ TRY...EXCEPT, ЧТОБЫ ОШИБКИ ПРОБРАСЫВАЛИСЬ ВЫШЕ <--

        EXCLUDE_KEYWORDS = {'vision', 'preview', 'exp',
                            'lite', 'tts', 'thinking', 'code', 'gemma'}
        all_models = [m.name.split('/')[-1] for m in genai.list_models()
                      if 'generateContent' in m.supported_generation_methods]

        if not show_all:
            filtered_models = []
            for model_name in all_models:
                if any(keyword in model_name for keyword in EXCLUDE_KEYWORDS):
                    continue
                if model_name[-4:].startswith('-') and model_name[-3:].isdigit():
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

            main_models.sort(key=sort_key)
            print(f"Итоговый список моделей для отображения: {main_models}")
            return main_models
