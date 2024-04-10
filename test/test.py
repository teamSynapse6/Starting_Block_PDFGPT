from flask import Flask, request, Response, jsonify
import openai

app = Flask(__name__)

# Replace 'your_api_key' with your actual OpenAI API key
openai.api_key = 'your_api_key'

@app.route('/ask', methods=['POST'])
def ask():
    data = request.json
    prompt = data.get('prompt')

    # The stream parameter is set to True to use the streaming API
    response = openai.ChatCompletion.create(
        model="gpt-4-turbo-preview",
        messages=[{"role": "user", "content": prompt}]
    )

    # Instead of yielding, we directly return the response here
    # The stream functionality will be handled on the client side
    return jsonify(response)

if __name__ == '__main__':
    app.run(debug=True)
