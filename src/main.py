from flask import Flask, request

from buy_assistant import BuyAssistant


app = Flask(__name__)


@app.route("/")
def hello():
    return "Hello world!"

@app.route("/chat", methods=["POST"])
def chat():
    # Getting the payload
    data = request.get_json()

    # Calling the buy assistant and returning the response
    return BuyAssistant().chat(data["message"])

if __name__ == "__main__":
    app.run(debug=True)