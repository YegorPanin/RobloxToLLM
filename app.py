from flask import Flask, request, jsonify
import sqlite3
import requests
import os
import datetime
import json
import base64
import uuid
import time  # Импортируем time для работы со временем

app = Flask(__name__)

DATABASE_NAME = 'Characters.db'
GIGACHAT_AUTHORIZATION_KEY = os.environ.get("GIGACHAT_AUTHORIZATION_KEY")
GIGACHAT_MODEL_NAME = "GigaChat:latest"
GIGACHAT_API_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"

# Глобальные переменные для кэширования Access Token и времени его истечения
access_token_cache = None
token_expiry_time = None

if not GIGACHAT_AUTHORIZATION_KEY:
    print("Внимание: Не найден GIGACHAT_AUTHORIZATION_KEY в переменных окружения.")
    print("Пожалуйста, установите переменную окружения GIGACHAT_AUTHORIZATION_KEY, чтобы использовать GigaChat API.")


def get_db_connection():
    print(f"DEBUG: {datetime.datetime.now()} - Вход в функцию get_db_connection")
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    print(f"DEBUG: {datetime.datetime.now()} - Выход из функции get_db_connection: Соединение установлено")
    return conn


@app.route('/api', methods=['POST'])
def handle_post_request():
    print(f"DEBUG: {datetime.datetime.now()} - Вход в функцию handle_post_request")
    if request.method == 'POST':
        data = request.get_json()
        char_name = data.get('charName')
        player_name = data.get('playerName')
        question = data.get('question')
        print(f"DEBUG: {datetime.datetime.now()} - handle_post_request: Получены данные запроса: {data}")

        if not all([char_name, player_name, question]):
            print(f"DEBUG: {datetime.datetime.now()} - Выход из handle_post_request с ошибкой: Недостаточно данных в запросе")
            return jsonify({'error': 'Недостаточно данных в запросе. Ожидаются charName, playerName, question'}), 400

        try:
            result = process_data(char_name, player_name, question)
            print(f"DEBUG: {datetime.datetime.now()} - Выход из handle_post_request: Успешно, ответ получен")
            print(f"DEBUG: {datetime.datetime.now()} - Ответ от process_data (начало): {result[:50]}...")
            return jsonify({'response': result}), 200
        except Exception as e:
            print(f"DEBUG: {datetime.datetime.now()} - Выход из handle_post_request с ошибкой: {e}")
            return jsonify({'error': str(e)}), 500
    else:
        print(f"DEBUG: {datetime.datetime.now()} - Выход из handle_post_request с ошибкой: Метод не поддерживается")
        return 'Метод не поддерживается', 405
    print(f"DEBUG: {datetime.datetime.now()} - Выход из функции handle_post_request (конец)")


def process_data(char_name, player_name, question):
    print(f"DEBUG: {datetime.datetime.now()} - Вход в функцию process_data, char_name: {char_name}, player_name: {player_name}, question: {question}")
    conn = get_db_connection()
    try:
        character_description = get_character_description(conn, char_name)
        if not character_description:
            error_message = f'Персонаж с именем "{char_name}" не найден.'
            print(f"DEBUG: {datetime.datetime.now()} - Выход из process_data с ошибкой: {error_message}")
            raise ValueError(error_message)

        message_history = get_message_history(conn, char_name, player_name)
        prompt = construct_prompt(char_name, character_description, message_history, question)
        llm_response_text = send_prompt_to_llm_api(prompt)
        save_message(conn, char_name, player_name, question, 'user_to_character')
        save_message(conn, char_name, player_name, llm_response_text, 'character_to_user')

        print(f"DEBUG: {datetime.datetime.now()} - Выход из функции process_data: Успешно")
        return llm_response_text
    except Exception as e:
        conn.rollback()
        print(f"DEBUG: {datetime.datetime.now()} - Выход из process_data с ошибкой: {e}")
        raise e
    finally:
        conn.close()
    print(f"DEBUG: {datetime.datetime.now()} - Выход из функции process_data (finally)")


def get_character_description(conn, character_name):
    print(f"DEBUG: {datetime.datetime.now()} - Вход в функцию get_character_description, character_name: {character_name}")
    cursor = conn.cursor()
    cursor.execute("SELECT character_description FROM Characters WHERE character_name = ?", (character_name,))
    result = cursor.fetchone()
    if result:
        description = result['character_description']
        print(f"DEBUG: {datetime.datetime.now()} - Выход из get_character_description: Персонаж найден, описание (начало): {description[:50]}...")
        return result['character_description']
    else:
        print(f"DEBUG: {datetime.datetime.now()} - Выход из get_character_description: Персонаж не найден")
        return None
    print(f"DEBUG: {datetime.datetime.now()} - Выход из функции get_character_description (finally)")


def get_message_history(conn, character_name, player_name):
    print(f"DEBUG: {datetime.datetime.now()} - Вход в функцию get_message_history, character_name: {character_name}, player_name: {player_name}")
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
    print(f"DEBUG: {datetime.datetime.now()} - Выход из функции get_message_history: История сообщений получена, кол-во: {len(history)}")
    return history
    print(f"DEBUG: {datetime.datetime.now()} - Выход из функции get_message_history (finally)")


def construct_prompt(character_name, character_description, message_history, current_question):
    print(f"DEBUG: {datetime.datetime.now()} - Вход в функцию construct_prompt, character_name: {character_name}, question (начало): {current_question[:50]}...")
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
    print(f"DEBUG: {datetime.datetime.now()} - Выход из функции construct_prompt: Промпт создан, длина: {len(prompt)}")
    return prompt
    print(f"DEBUG: {datetime.datetime.now()} - Выход из функции construct_prompt (finally)")

def get_gigachat_access_token():
    global access_token_cache, token_expiry_time

    print(f"DEBUG: {datetime.datetime.now()} - Вход в функцию get_gigachat_access_token")

    if access_token_cache and token_expiry_time and datetime.datetime.now() < token_expiry_time:
        print(f"DEBUG: {datetime.datetime.now()} - get_gigachat_access_token: Используем кэшированный Access Token (действителен до {token_expiry_time})")
        return access_token_cache

    oauth_url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    authorization_key = GIGACHAT_AUTHORIZATION_KEY

    if not authorization_key:
        error_message = "Не найден GIGACHAT_AUTHORIZATION_KEY в переменных окружения.  Нужен Authorization key для получения Access Token."
        print(f"DEBUG: {datetime.datetime.now()} - Выход из get_gigachat_access_token с ошибкой: {error_message}")
        raise Exception(error_message)

    headers_oauth = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json',
        'RqUID': str(uuid.uuid4()), # Generate random UUID for RqUID
        'Authorization': 'Basic ' + base64.b64encode(authorization_key.encode('utf-8')).decode('utf-8')
    }
    payload_oauth = {'scope': 'GIGACHAT_API_PERS'}

    print(f"DEBUG: {datetime.datetime.now()} - get_gigachat_access_token: OAuth URL: {oauth_url}") # **DEBUG: Print OAuth URL**
    print(f"DEBUG: {datetime.datetime.now()} - get_gigachat_access_token: OAuth Headers: {headers_oauth}") # **DEBUG: Print OAuth Headers**
    print(f"DEBUG: {datetime.datetime.now()} - get_gigachat_access_token: OAuth Payload: {payload_oauth}") # **DEBUG: Print OAuth Payload**


    try:
        response_oauth = requests.request("POST", oauth_url, headers=headers_oauth, data=payload_oauth, verify=False) # verify=False - for debugging
        response_oauth.raise_for_status()

        access_token_json = response_oauth.json()
        access_token = access_token_json['access_token']
        expires_in = access_token_json['expires_in']

        access_token_cache = access_token
        token_expiry_time = datetime.datetime.now() + datetime.timedelta(seconds=expires_in - 60)

        print(f"DEBUG: {datetime.datetime.now()} - Выход из функции get_gigachat_access_token: Access Token успешно получен и кэширован (действителен до {token_expiry_time}), начало: {access_token[:20]}...")
        return access_token

    except requests.exceptions.RequestException as e:
        error_message = f"Ошибка при получении Access Token от GigaChat API (oauth): {e}.  Response text: {response_oauth.text if 'response_oauth' in locals() else 'No response text available'}" # **DEBUG: Print response text**
        print(f"DEBUG: {datetime.datetime.now()} - Выход из get_gigachat_access_token с ошибкой requests: {error_message}")
        raise Exception(error_message)
    except KeyError as e:
        error_message = f"Ошибка при разборе JSON ответа Access Token API (oauth) (KeyError): {e}. Проверьте структуру JSON ответа."
        print(f"DEBUG: {datetime.datetime.now()} - Выход из get_gigachat_access_token с ошибкой KeyError: {error_message}")
        raise Exception(error_message)
    except Exception as e:
        error_message = f"Неизвестная ошибка при получении Access Token от GigaChat API (oauth): {e}"
        print(f"DEBUG: {datetime.datetime.now()} - Выход из get_gigachat_access_token с неизвестной ошибкой: {error_message}")
        raise Exception(error_message)
    print(f"DEBUG: {datetime.datetime.now()} - Выход из функции get_gigachat_access_token (finally)")

    except requests.exceptions.RequestException as e:
        error_message = f"Ошибка при получении Access Token от GigaChat API (oauth): {e}"
        print(f"DEBUG: {datetime.datetime.now()} - Выход из get_gigachat_access_token с ошибкой requests: {error_message}")
        raise Exception(error_message)
    except KeyError as e:
        error_message = f"Ошибка при разборе JSON ответа Access Token API (oauth) (KeyError): {e}. Проверьте структуру JSON ответа."
        print(f"DEBUG: {datetime.datetime.now()} - Выход из get_gigachat_access_token с ошибкой KeyError: {error_message}")
        raise Exception(error_message)
    except Exception as e:
        error_message = f"Неизвестная ошибка при получении Access Token от GigaChat API (oauth): {e}"
        print(f"DEBUG: {datetime.datetime.now()} - Выход из get_gigachat_access_token с неизвестной ошибкой: {error_message}")
        raise Exception(error_message)
    print(f"DEBUG: {datetime.datetime.now()} - Выход из функции get_gigachat_access_token (finally)")


def send_prompt_to_llm_api(prompt):
    print(f"DEBUG: {datetime.datetime.now()} - Вход в функцию send_prompt_to_llm_api, prompt (начало): {prompt[:50]}...")

    url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"

    try:
        access_token = get_gigachat_access_token() # Get Access Token (теперь с кэшированием и обновлением)

        headers = {
            'Accept': 'application/json',
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        payload = {
            "model_id": GIGACHAT_MODEL_NAME,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        }

        print(f"DEBUG: {datetime.datetime.now()} -  send_prompt_to_llm_api: Headers (using Access Token): {headers}")

        response = requests.request("POST", url, headers=headers, json=payload, verify=False) # verify=False - for debugging
        response.raise_for_status()
        llm_response_json = response.json()
        llm_response_text = llm_response_json['choices'][0]['message']['content']

        print(f"DEBUG: {datetime.datetime.now()} - Выход из функции send_prompt_to_llm_api: Ответ от API получен, content (начало): {llm_response_text[:50]}...")
        return llm_response_text


    except requests.exceptions.RequestException as e:
        error_message = f"Ошибка при обращении к GigaChat API через библиотеку 'requests': {e}"
        print(f"DEBUG: {datetime.datetime.now()} - Выход из send_prompt_to_llm_api с ошибкой requests: {error_message}")
        raise Exception(error_message)
    except KeyError as e:
        error_message = f"Ошибка при разборе ответа GigaChat API JSON (KeyError): {e}. Проверьте структуру JSON ответа."
        print(f"DEBUG: {datetime.datetime.now()} - Выход из send_prompt_to_llm_api с ошибкой KeyError: {error_message}")
        raise Exception(error_message)
    except Exception as e:
        error_message = f"Неизвестная ошибка при обращении к GigaChat API: {e}"
        print(f"DEBUG: {datetime.datetime.now()} - Выход из send_prompt_to_llm_api с неизвестной ошибкой: {error_message}")
    print(f"DEBUG: {datetime.datetime.now()} - Выход из функции send_prompt_to_llm_api (finally)")


def save_message(conn, character_name, player_name, message_text, message_direction):
    print(f"DEBUG: {datetime.datetime.now()} - Вход в функцию save_message, char_name: {character_name}, player_name: {player_name}, direction: {message_direction}")
    user_id = get_or_create_user(conn, player_name)
    if user_id is None:
        error_message = f"Не удалось получить или создать User для имени: {player_name}"
        print(f"DEBUG: {datetime.datetime.now()} - Выход из save_message с ошибкой: {error_message}")
        raise Exception(error_message)

    character_id = get_character_id_by_name(conn, character_name)
    if character_id is None:
        error_message = f"Персонаж с именем '{character_name}' не найден при сохранении сообщения."
        print(f"DEBUG: {datetime.datetime.now()} - Выход из save_message с ошибкой: {error_message}")
        raise Exception(error_message)

    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO Messages (character_id, user_id, message_text, message_direction)
        VALUES (?, ?, ?, ?)
    """, (character_id, user_id, message_text, message_direction))
    conn.commit()
    print(f"DEBUG: {datetime.datetime.now()} - Выход из функции save_message: Сообщение сохранено")
    print(f"DEBUG: {datetime.datetime.now()} - Выход из функции save_message (finally)")


def get_or_create_user(conn, player_name):
    print(f"DEBUG: {datetime.datetime.now()} - Вход в функцию get_or_create_user, player_name: {player_name}")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM Users WHERE user_name = ?", (player_name,))
    result = cursor.fetchone()
    if result:
        user_id = result['user_id']
        print(f"DEBUG: {datetime.datetime.now()} - Выход из get_or_create_user: Пользователь найден, user_id: {user_id}")
        return result['user_id']
    else:
        cursor.execute("INSERT INTO Users (user_name) VALUES (?)", (player_name,))
        conn.commit()
        user_id = cursor.lastrowid
        print(f"DEBUG: {datetime.datetime.now()} - Выход из get_or_create_user: Пользователь создан, user_id: {user_id}")
        return user_id
    print(f"DEBUG: {datetime.datetime.now()} - Выход из функции get_or_create_user (finally)")


def get_character_id_by_name(conn, character_name):
    print(f"DEBUG: {datetime.datetime.now()} - Вход в функцию get_character_id_by_name, character_name: {character_name}")
    cursor = conn.cursor()
    cursor.execute("SELECT character_id FROM Characters WHERE character_name = ?", (character_name,))
    result = cursor.fetchone()
    if result:
        character_id = result['character_id']
        print(f"DEBUG: {datetime.datetime.now()} - Выход из get_character_id_by_name: character_id найден: {character_id}")
        return character_id
    else:
        print(f"DEBUG: {datetime.datetime.now()} - Выход из get_character_id_by_name: Персонаж не найден")
        return None
    print(f"DEBUG: {datetime.datetime.now()} - Выход из функции get_character_id_by_name (finally)")


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
