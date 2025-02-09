from flask import Flask, request

app = Flask(__name__)

@app.route('/api/endpoint', methods=['POST'])
def handle_post_request():
    if request.method == 'POST':
        data = request.get_json()  # Получаем данные из запроса в формате JSON
        # Обрабатываем полученные данные
        result = process_data(data)
        return jsonify(result), 200  # Возвращаем результат обработки и код состояния 200
    else:
        return 'Метод не поддерживается', 405  # Возвращаем ошибку, если метод запроса не POST

def process_data(data):
    # Здесь ваша логика обработки данных
    # Пример:
    if 'name' in data:
        name = data['name']
        return {'message': f'Привет, {name}!'}
    else:
        return {'message': 'Не указано имя'}

if __name__ == '__main__':
    app.run(debug=True)