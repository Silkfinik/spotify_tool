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
        Получает список моделей и применяет фильтр.
        (ОТЛАДОЧНАЯ ВЕРСИЯ)
        """
        if not self.is_active:
            raise ConnectionError("AI-ассистент не был инициализирован.")

        print("\n--- ОТЛАДКА: Запрос списка AI моделей ---")

        try:
            # Сначала получаем абсолютно все модели от API
            all_listed_models = list(genai.list_models())

            # --> ГЛАВНЫЙ ОТЛАДОЧНЫЙ ВЫВОД <--
            print(f"DEBUG: Получено {len(all_listed_models)} моделей от API.")
            if all_listed_models:
                print("--- НАЧАЛО СЫРОГО ОТВЕТА API (первые 5) ---")
                for i, m in enumerate(all_listed_models[:5]):
                    print(
                        f"  - Модель {i+1}: name={m.name}, display_name={m.display_name}, methods={m.supported_generation_methods}")
                print("--- КОНЕЦ СЫРОГО ОТВЕТА API ---\n")

            # Далее идет наша стандартная логика фильтрации
            EXCLUDE_KEYWORDS = {'vision', 'preview', 'exp',
                                'lite', 'tts', 'thinking', 'code', 'gemma'}
            main_models = []

            for m in all_listed_models:
                if 'generateContent' in m.supported_generation_methods:
                    model_name = m.name.split('/')[-1]
                    if not show_all:
                        if any(keyword in model_name for keyword in EXCLUDE_KEYWORDS):
                            continue
                        if model_name[-4:].startswith('-') and model_name[-3:].isdigit():
                            continue
                    main_models.append(model_name)

            def sort_key(name):
                family_prio = 0 if 'gemini' in name else 1
                tier_prio = 0 if 'pro' in name else 1
                latest_prio = 0 if 'latest' in name else 1
                version_match = re.search(r'(\d\.\d|\d)', name)
                version = float(version_match.group(1)) if version_match else 0
                return (family_prio, -version, tier_prio, latest_prio)

            main_models.sort(key=sort_key)
            print(f"Отфильтрованный список для UI: {main_models}")
            return main_models

        except Exception as e:
            print(
                f"---!!! КРИТИЧЕСКАЯ ОШИБКА при вызове genai.list_models(): {e} !!!---")
            raise
