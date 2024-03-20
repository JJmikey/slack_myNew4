from flask import Flask, request, jsonify
from slack_sdk.oauth import AuthorizeUrlGenerator
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

import os 
import openai

app = Flask(__name__)


# 你的 OpenAI API key
openai.api_key = os.getenv("OPENAI_API_KEY")

slack_bot_token = os.environ["SLACK_BOT_TOKEN"] # 用以調用 Slack API 
client = WebClient(token=slack_bot_token)
print(os.getenv("SLACK_BOT_TOKEN"))

slack_client_id = os.environ["SLACK_CLIENT_ID"]
slack_client_secret = os.environ["SLACK_CLIENT_SECRET"]

@app.route("/slack/events", methods=["POST"])
def slack_events():
    payload = request.json
    if "challenge" in payload:
        return payload["challenge"], 200  # 马上返回所需要的`challenge`参数的值
    else:
        # 在這裡處理其它事件
        event = payload.get("event", {})

        # 當收到訊息時
        if payload.get("type") == "event_callback" and event.get("type") == "message":
            channel_id = event.get("channel")
            bot_id = event.get("bot_id")

            # 如果 bot_id 屬性存在，說明這條消息由 Bot 發送
            if bot_id:
                return jsonify({}), 200 

            # Use OpenAI GPT-4 to generate a message
            prompt = event.get('text')
            response = openai.Completion.create(engine="gpt-4-1106-preview", prompt=prompt, max_tokens=4000)


            client.chat_postMessage(channel=channel_id, text=response.choices[0].text.strip())
            return jsonify({}), 200 
        

@app.route("/slack/auth", methods=["GET"])
def slack_oauth():
    code = request.args.get('code')
    client = WebClient()
    response = client.oauth_v2_access(
        client_id=slack_client_id,
        client_secret=slack_client_secret,
        code=code,
        #redirect_uri=slack_redirect_uri  # Include this only if you have set a redirect URI
    )
    # Access token should be stored securely in your application.
    # Here, for example, save it in the environment variable. This is just for illustration; don't store tokens in plain text.
    access_token = response.get('access_token')
    os.environ["SLACK_BOT_TOKEN"] = access_token

    return jsonify({"message": "OAuth flow completed"}), 200

@app.route("/site-map")
def site_map():
    output = []
    for rule in app.url_map.iter_rules():
        methods = ', '.join(sorted(rule.methods))
        output.append(f"{rule} ({methods})")
    return "<br>".join(sorted(output))


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080))) #for deploy on vercel