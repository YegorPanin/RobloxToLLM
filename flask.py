from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/')
def home():
    return "Сервер работает!"

@app.route('/data', methods=['POST'])
def receive_data():
    data = request.json
    # Здесь вы можете обрабатывать данные, которые получаете
    print("Полученные данные:", data)
    return jsonify({"status": "успешно", "received": data}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)