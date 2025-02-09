from flask import Flask, request, jsonify
import sqlite3
import requests
import os # Импортируем библиотеку os для доступа к переменным окружения

app = Flask(__name__)

DATABASE_NAME = 'Characters.db'
GROQ_API_ENDPOINT = 'https://api.groq.com/openai/v1/chat/completions' # Endpoint Groq API для Chat Completions
GROQ_API_KEY = os.environ.get("GROQ_API_KEY") # Получаем API-ключ из переменной окружения. **ВАЖНО: Настройте переменную окружения!**
GROQ_MODEL_NAME = "llama3-8b-8192" # Или другая поддерживаемая модель Groq, например "mixtral-8x7b-32768"

if not GROQ_API_KEY:
    print("Внимание: Не найден GROQ_API_KEY в переменных окружения.")
    print("Пожалуйста, установите переменную окружения GROQ_API_KEY, чтобы использовать Groq API.")
    # Сервер запустится, но запросы к LLM API не будут работать, пока не будет установлен ключ.


def get_db_connection():
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/api', methods=['POST'])
def handle_post_request():
    if request.method == 'POST':
        data = request.get_json()
        char_name = data.get('charName')
        player_name = data.get('playerName')
        question = data.get('question')

        if not all([char_name, player_name, question]):
            return jsonify({'error': 'Недостаточно данных в запросе. Ожидаются charName, playerName, question'}), 400

        try:
            result = process_data(char_name, player_name, question)
            return jsonify({'response': result}), 200
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    else:
        return 'Метод не поддерживается', 405

def process_data(char_name, player_name, question):
    conn = get_db_connection()
    try:
        character_description = get_character_description(conn, char_name)
        if not character_description:
            raise ValueError(f'Персонаж с именем "{char_name}" не найден.')

        message_history = get_message_history(conn, char_name, player_name)

        prompt = construct_prompt(char_name, character_description, message_history, question)

        llm_response_text = send_prompt_to_llm_api(prompt)

        save_message(conn, char_name, player_name, question, 'user_to_character')
        save_message(conn, char_name, player_name, llm_response_text, 'character_to_user')

        return llm_response_text
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def get_character_description(conn, character_name):
    cursor = conn.cursor()
    cursor.execute("SELECT character_description FROM Characters WHERE character_name = ?", (character_name,))
    result = cursor.fetchone()
    if result:
        return result['character_description']
    return None

def get_message_history(conn, character_name, player_name):
    cursor = conn.cursor()
    cursor.execute("""
        SELECT message_text, message_direction
        FROM Messages
        WHERE character_id = (SELECT character_id FROM Characters WHERE character_name = ?)
          AND user_id = (SELECT user_id FROM Users WHERE user_name = ?)
        ORDER BY message_timestamp ASC
    """, (char_name, player_name))
    history = []
    for row in cursor.fetchall():
        direction = "Игрок" if row['message_direction'] == 'user_to_character' else character_name
        history.append(f"{direction}: {message['message_text']}")
    return history

def construct_prompt(character_name, character_description, message_history, current_question):
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
    return "".join(prompt_parts)

def send_prompt_to_llm_api(prompt):
    """Отправляет промпт к Groq API и возвращает ответ."""
    headers = {
        'Authorization': f'Bearer {GROQ_API_KEY}', # Добавляем API-ключ в заголовок Authorization
        'Content-Type': 'application/json'
    }
    payload = {
        "model": GROQ_MODEL_NAME, # Указываем модель Groq, которую хотим использовать
        "messages": [{"role": "user", "content": prompt}] # Формируем запрос в формате Chat Completions API
    }
    try:
        response = requests.post(GROQ_API_ENDPOINT, headers=headers, json=payload)
        response.raise_for_status()
        llm_response = response.json()

        # Groq API возвращает ответ в формате choices[0].message.content
        if llm_response.get('choices') and llm_response['choices'][0].get('message'):
            return llm_response['choices'][0]['message']['content']
        else:
            raise ValueError("Не удалось извлечь текст ответа из ответа Groq API")

    except requests.exceptions.RequestException as e:
        raise Exception(f"Ошибка при обращении к Groq API: {e}")
    except ValueError as e:
        raise Exception(f"Ошибка обработки ответа от Groq API: {e}. Ответ API: {response.text}")


def save_message(conn, character_name, player_name, message_text, message_direction):
    user_id = get_or_create_user(conn, player_name)
    if user_id is None:
        raise Exception(f"Не удалось получить или создать User для имени: {player_name}")

    character_id = get_character_id_by_name(conn, character_name)
    if character_id is None:
        raise Exception(f"Персонаж с именем '{character_name}' не найден при сохранении сообщения.")


    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO Messages (character_id, user_id, message_text, message_direction)
        VALUES (?, ?, ?, ?)
    """, (character_id, user_id, message_text, message_direction))
    conn.commit()

def get_or_create_user(conn, player_name):
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM Users WHERE user_name = ?", (player_name,))
    result = cursor.fetchone()
    if result:
        return result['user_id']
    else:
        cursor.execute("INSERT INTO Users (user_name) VALUES (?)", (player_name,))
        conn.commit()
        return cursor.lastrowid

def get_character_id_by_name(conn, character_name):
    cursor = conn.cursor()
    cursor.execute("SELECT character_id FROM Characters WHERE character_name = ?", (character_name,))
    result = cursor.fetchone()
    if result:
        return result['character_id']
    return None


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
