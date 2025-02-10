from flask import Flask, request, jsonify
import sqlite3
import os
import datetime
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_gigachat.chat_models import GigaChat

app = Flask(__name__)

DATABASE_NAME = 'Characters.db'
GIGACHAT_AUTHORIZATION_KEY = os.environ.get("GIGACHAT_AUTHORIZATION_KEY")
GIGACHAT_MODEL_NAME = "GigaChat:latest"

# Инициализация модели GigaChat через Langchain
llm = GigaChat(
    credentials=GIGACHAT_AUTHORIZATION_KEY, # Используем Authorization Key из переменных окружения
    verify_ssl_certs=False, # verify_ssl_certs=False - для отладки, в production лучше убрать или True
    model=GIGACHAT_MODEL_NAME # Указываем модель
)

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

            # **Явно кодируем и декодируем в UTF-8 перед jsonify**
            result_utf8_bytes = result.encode('utf-8')
            result_utf8_string = result_utf8_bytes.decode('utf-8')

            # Отправляем JSON ответ, указав кодировку UTF-8 через mimetype
            return jsonify({'response': result_utf8_string},  mimetype='application/json; charset=utf-8'), 200
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


def send_prompt_to_llm_api(prompt):
    print(f"DEBUG: {datetime.datetime.now()} - Вход в функцию send_prompt_to_llm_api, prompt (начало): {prompt[:50]}...")

    try:
        messages = [ # Формируем список сообщений Langchain
            SystemMessage(content="Ты - игровой персонаж."), # Системное сообщение (можно убрать, если не нужно)
            HumanMessage(content=prompt) # Сообщение пользователя с промптом
        ]
        response = llm.invoke(messages) # Вызов Langchain LLM
        llm_response_text_bytes = response.content.encode('utf-8') # Сначала кодируем в байты (на всякий случай)
        llm_response_text = llm_response_text_bytes.decode('utf-8') # Затем декодируем как UTF-8

        print(f"DEBUG: {datetime.datetime.now()} - Выход из функции send_prompt_to_llm_api: Ответ от API получен, content (начало): {llm_response_text[:50]}...")
        return llm_response_text

    except Exception as e: # Ловим общие исключения для обработки ошибок Langchain
        error_message = f"Ошибка при обращении к GigaChat API через Langchain: {e}"
        print(f"DEBUG: {datetime.datetime.now()} - Выход из send_prompt_to_llm_api с ошибкой Langchain: {error_message}")
        raise Exception(error_message)
    print(f"DEBUG: {datetime.datetime.now()} - Выход из функции send_prompt_to_llm_api (finally)")


# Функция get_gigachat_access_token больше не нужна, Langchain управляет токенами

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
