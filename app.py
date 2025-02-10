from flask import Flask, request, jsonify
import sqlite3
import requests
import os  # Импортируем библиотеку os для доступа к переменным окружения
import datetime  # Импортируем модуль datetime для получения текущего времени
import json # Импортируем модуль json для работы с JSON

app = Flask(__name__)

DATABASE_NAME = 'Characters.db'
GIGACHAT_API_KEY = os.environ.get("GIGACHAT_API_KEY")  # Получаем API-ключ из переменной окружения. **ВАЖНО: Настройте переменную окружения!**
GIGACHAT_MODEL_NAME = "GigaChat:latest"  # Или другая поддерживаемая модель GigaChat

# URL для запросов к GigaChat API (из примера кода)
GIGACHAT_API_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"

if not GIGACHAT_API_KEY:
    print("Внимание: Не найден GIGACHAT_API_KEY в переменных окружения.")
    print("Пожалуйста, установите переменную окружения GIGACHAT_API_KEY, чтобы использовать GigaChat API.")
    # Сервер запустится, но запросы к LLM API не будут работать, пока не будет установлен ключ.


def get_db_connection():
    print(f"DEBUG: {datetime.datetime.now()} - Вход в функцию get_db_connection")  # Отладка: Вход
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    print(f"DEBUG: {datetime.datetime.now()} - Выход из функции get_db_connection: Соединение установлено")  # Отладка: Успешный выход
    return conn
    print(f"DEBUG: {datetime.datetime.now()} - Выход из функции get_db_connection (finally)")  # Отладка: Выход finally


@app.route('/api', methods=['POST'])
def handle_post_request():
    print(f"DEBUG: {datetime.datetime.now()} - Вход в функцию handle_post_request")  # Отладка: Вход в функцию
    if request.method == 'POST':
        data = request.get_json()
        char_name = data.get('charName')
        player_name = data.get('playerName')
        question = data.get('question')
        print(f"DEBUG: {datetime.datetime.now()} - handle_post_request: Получены данные запроса: {data}")  # Отладка: Данные запроса

        if not all([char_name, player_name, question]):
            print(f"DEBUG: {datetime.datetime.now()} - Выход из handle_post_request с ошибкой: Недостаточно данных в запросе")  # Отладка: Выход с ошибкой
            return jsonify({'error': 'Недостаточно данных в запросе. Ожидаются charName, playerName, question'}), 400

        try:
            result = process_data(char_name, player_name, question)
            print(f"DEBUG: {datetime.datetime.now()} - Выход из handle_post_request: Успешно, ответ получен")  # Отладка: Успешный выход
            print(f"DEBUG: {datetime.datetime.now()} - Ответ от process_data (начало): {result[:50]}...")  # Показываем начало ответа для примера
            return jsonify({'response': result}), 200
        except Exception as e:
            print(f"DEBUG: {datetime.datetime.now()} - Выход из handle_post_request с ошибкой: {e}")  # Отладка: Выход с ошибкой Exception
            return jsonify({'error': str(e)}), 500
    else:
        print(f"DEBUG: {datetime.datetime.now()} - Выход из handle_post_request с ошибкой: Метод не поддерживается")  # Отладка: Выход с ошибкой Method Not Allowed
        return 'Метод не поддерживается', 405
    print(f"DEBUG: {datetime.datetime.now()} - Выход из функции handle_post_request (конец)")  # Отладка: Выход из функции (нормальный, если POST)


def process_data(char_name, player_name, question):
    print(f"DEBUG: {datetime.datetime.now()} - Вход в функцию process_data, char_name: {char_name}, player_name: {player_name}, question: {question}")  # Отладка: Вход
    conn = get_db_connection()
    try:
        character_description = get_character_description(conn, char_name)
        if not character_description:
            error_message = f'Персонаж с именем "{char_name}" не найден.'
            print(f"DEBUG: {datetime.datetime.now()} - Выход из process_data с ошибкой: {error_message}")  # Отладка: Выход с ошибкой
            raise ValueError(error_message)

        message_history = get_message_history(conn, char_name, player_name)
        prompt = construct_prompt(char_name, character_description, message_history, question)
        llm_response_text = send_prompt_to_llm_api(prompt)
        save_message(conn, char_name, player_name, question, 'user_to_character')
        save_message(conn, char_name, player_name, llm_response_text, 'character_to_user')

        print(f"DEBUG: {datetime.datetime.now()} - Выход из функции process_data: Успешно")  # Отладка: Успешный выход
        return llm_response_text
    except Exception as e:
        conn.rollback()
        print(f"DEBUG: {datetime.datetime.now()} - Выход из process_data с ошибкой: {e}")  # Отладка: Выход с ошибкой Exception
        raise e
    finally:
        conn.close()
    print(f"DEBUG: {datetime.datetime.now()} - Выход из функции process_data (finally)")  # Отладка: Выход finally


def get_character_description(conn, character_name):
    print(f"DEBUG: {datetime.datetime.now()} - Вход в функцию get_character_description, character_name: {character_name}")  # Отладка: Вход
    cursor = conn.cursor()
    cursor.execute("SELECT character_description FROM Characters WHERE character_name = ?", (character_name,))
    result = cursor.fetchone()
    if result:
        description = result['character_description']
        print(f"DEBUG: {datetime.datetime.now()} - Выход из get_character_description: Персонаж найден, описание (начало): {description[:50]}...")  # Отладка: Успешный выход
        return result['character_description']
    else:
        print(f"DEBUG: {datetime.datetime.now()} - Выход из get_character_description: Персонаж не найден")  # Отладка: Выход, персонаж не найден
        return None
    print(f"DEBUG: {datetime.datetime.now()} - Выход из функции get_character_description (finally)")  # Отладка: Выход finally


def get_message_history(conn, character_name, player_name):
    print(f"DEBUG: {datetime.datetime.now()} - Вход в функцию get_message_history, character_name: {character_name}, player_name: {player_name}")  # Отладка: Вход
    cursor = conn.cursor()
    cursor.execute("""
        SELECT message_text, message_direction
        FROM Messages
        WHERE character_id = (SELECT character_id FROM Characters WHERE character_name = ?)
            AND user_id = (SELECT user_id FROM Users WHERE user_name = ?)
        ORDER BY message_timestamp ASC
    """, (character_name, player_name))
    history = []
    for row in cursor.fetchall():
        direction = "Игрок" if row['message_direction'] == 'user_to_character' else character_name
        history.append(f"{direction}: {row['message_text']}")
    print(f"DEBUG: {datetime.datetime.now()} - Выход из функции get_message_history: История сообщений получена, кол-во: {len(history)}")  # Отладка: Успешный выход
    return history
    print(f"DEBUG: {datetime.datetime.now()} - Выход из функции get_message_history (finally)")  # Отладка: Выход finally


def construct_prompt(character_name, character_description, message_history, current_question):
    print(f"DEBUG: {datetime.datetime.now()} - Вход в функцию construct_prompt, character_name: {character_name}, question (начало): {current_question[:50]}...")  # Отладка: Вход
    prompt_parts = [
        f"Тебя зовут: {character_name}\n",
        f"Твой характер: {character_description}\n",
        "Представь себя персонажем игры. Отвечай на вопросы, учитывая свой характер. ",
        "Если вопрос не соответствует твоему характеру и истории, ни в коем случае НЕ ОТВЕЧАЙ на него.\n",
        "История вопросов и ответов:\n"
    ]
    if message_history:
        prompt_parts.append("\n".join(message_history))
        prompt_parts.append("\n")

    prompt_parts.append(f"Текущий вопрос:\n{current_question}")
    prompt = "".join(prompt_parts)
    print(f"DEBUG: {datetime.datetime.now()} - Выход из функции construct_prompt: Промпт создан, длина: {len(prompt)}")  # Отладка: Успешный выход
    return prompt
    print(f"DEBUG: {datetime.datetime.now()} - Выход из функции construct_prompt (finally)")  # Отладка: Выход finally


def send_prompt_to_llm_api(prompt):
    print(f"DEBUG: {datetime.datetime.now()} - Вход в функцию send_prompt_to_llm_api, prompt (начало): {prompt[:50]}...")  # Отладка: Вход
    """Отправляет промпт к GigaChat API и возвращает ответ, используя библиотеку 'requests' и структуру запроса из документации.

    **ВНИМАНИЕ: Временно отключена проверка SSL-сертификата (verify=False) для обхода ошибки SSLError.
    Это НЕБЕЗОПАСНО для production-приложений.  В production нужно настроить проверку сертификатов!**
    """

    url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions" # Используем URL из примера

    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {GIGACHAT_API_KEY}', # Используем API-ключ GigaChat из переменной среды
        'Content-Type': 'application/json' # Важно указать Content-Type: application/json для POST-запросов с JSON-телом
    }

    payload = { # Формируем JSON payload для POST запроса к /chat/completions
        "model_id": GIGACHAT_MODEL_NAME, # Используем имя модели GigaChat из переменной среды
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ]
    }

    print(f"DEBUG: {datetime.datetime.now()} -  send_prompt_to_llm_api: GIGACHAT_API_KEY value: '{GIGACHAT_API_KEY}'") # **DEBUG: Print API Key**
    print(f"DEBUG: {datetime.datetime.now()} -  send_prompt_to_llm_api: Headers: {headers}") # **DEBUG: Print Headers**

    try:
        response = requests.request("POST", url, headers=headers, json=payload, verify=False) # **verify=False - Отключение проверки SSL!**
        response.raise_for_status()  # Проверка на HTTP ошибки
        llm_response_json = response.json()

        # Извлекаем текст ответа из JSON структуры ответа GigaChat (путь может отличаться, проверяйте документацию)
        llm_response_text = llm_response_json['choices'][0]['message']['content']

        print(f"DEBUG: {datetime.datetime.now()} - Выход из функции send_prompt_to_llm_api: Ответ от API получен, content (начало): {llm_response_text[:50]}...")  # Отладка: Успешный выход
        return llm_response_text

    except requests.exceptions.RequestException as e:
        error_message = f"Ошибка при обращении к GigaChat API через библиотеку 'requests': {e}"
        print(f"DEBUG: {datetime.datetime.now()} - Выход из send_prompt_to_llm_api с ошибкой requests: {error_message}")  # Отладка: Выход с ошибкой Exception
        raise Exception(error_message)
    except KeyError as e: # Обработка ошибки KeyError, если структура JSON ответа не соответствует ожиданиям
        error_message = f"Ошибка при разборе ответа GigaChat API JSON (KeyError): {e}. Проверьте структуру JSON ответа."
        print(f"DEBUG: {datetime.datetime.now()} - Выход из send_prompt_to_llm_api с ошибкой KeyError: {error_message}")
        raise Exception(error_message)
    except Exception as e: # Ловим общие исключения на всякий случай
        error_message = f"Неизвестная ошибка при обращении к GigaChat API: {e}"
        print(f"DEBUG: {datetime.datetime.now()} - Выход из send_prompt_to_llm_api с неизвестной ошибкой: {error_message}")
        raise Exception(error_message)
    print(f"DEBUG: {datetime.datetime.now()} - Выход из функции send_prompt_to_llm_api (finally)")  # Отладка: Выход finally


def save_message(conn, character_name, player_name, message_text, message_direction):
    print(f"DEBUG: {datetime.datetime.now()} - Вход в функцию save_message, char_name: {character_name}, player_name: {player_name}, direction: {message_direction}")  # Отладка: Вход
    user_id = get_or_create_user(conn, player_name)
    if user_id is None:
        error_message = f"Не удалось получить или создать User для имени: {player_name}"
        print(f"DEBUG: {datetime.datetime.now()} - Выход из save_message с ошибкой: {error_message}")  # Отладка: Выход с ошибкой
        raise Exception(error_message)

    character_id = get_character_id_by_name(conn, character_name)
    if character_id is None:
        error_message = f"Персонаж с именем '{character_name}' не найден при сохранении сообщения."
        print(f"DEBUG: {datetime.datetime.now()} - Выход из save_message с ошибкой: {error_message}")  # Отладка: Выход с ошибкой
        raise Exception(error_message)

    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO Messages (character_id, user_id, message_text, message_direction)
        VALUES (?, ?, ?, ?)
    """, (character_id, user_id, message_text, message_direction))
    conn.commit()
    print(f"DEBUG: {datetime.datetime.now()} - Выход из функции save_message: Сообщение сохранено")  # Отладка: Успешный выход
    print(f"DEBUG: {datetime.datetime.now()} - Выход из функции save_message (finally)")  # Отладка: Выход finally

def get_or_create_user(conn, player_name):
    print(f"DEBUG: {datetime.datetime.now()} - Вход в функцию get_or_create_user, player_name: {player_name}")  # Отладка: Вход
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM Users WHERE user_name = ?", (player_name,))
    result = cursor.fetchone()
    if result:
        user_id = result['user_id']
        print(f"DEBUG: {datetime.datetime.now()} - Выход из get_or_create_user: Пользователь найден, user_id: {user_id}")  # Отладка: Успешный выход
        return result['user_id']
    else:
        cursor.execute("INSERT INTO Users (user_name) VALUES (?)", (player_name,))
        conn.commit()
        user_id = cursor.lastrowid
        print(f"DEBUG: {datetime.datetime.now()} - Выход из get_or_create_user: Пользователь создан, user_id: {user_id}")  # Отладка: Успешный выход
        return user_id
    print(f"DEBUG: {datetime.datetime.now()} - Выход из функции get_or_create_user (finally)")  # Отладка: Выход finally

def get_character_id_by_name(conn, character_name):
    print(f"DEBUG: {datetime.datetime.now()} - Вход в функцию get_character_id_by_name, character_name: {character_name}")  # Отладка: Вход
    cursor = conn.cursor()
    cursor.execute("SELECT character_id FROM Characters WHERE character_name = ?", (character_name,))
    result = cursor.fetchone()
    if result:
        character_id = result['character_id']
        print(f"DEBUG: {datetime.datetime.now()} - Выход из get_character_id_by_name: character_id найден: {character_id}")  # Отладка: Успешный выход
        return character_id
    else:
        print(f"DEBUG: {datetime.datetime.now()} - Выход из get_character_id_by_name: Персонаж не найден")  # Отладка: Выход, персонаж не найден
        return None
    print(f"DEBUG: {datetime.datetime.now()} - Выход из функции get_character_id_by_name (finally)")  # Отладка: Выход finally


if __name__ == '__main__':
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Characters';")
    if not cursor.fetchone():
        print("Таблица Characters не найдена, создаем...")
        with open('init_db_sqlite.sql', 'r') as f:
            sql_script = f.read()
            cursor.executescript(sql_script)
        print("Таблицы Characters, Users и Messages созданы.")
    else:
        print("Таблицы Characters, Users и Messages уже существуют.")

    conn.close()
    app.run(host='0.0.0.0', debug=False)
