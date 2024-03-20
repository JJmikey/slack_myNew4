from flask import Flask, request, jsonify
from slack_sdk.oauth import AuthorizeUrlGenerator
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

import os 

app = Flask(__name__)

slack_bot_token = os.environ["SLACK_BOT_TOKEN"] # 用以調用 Slack API 
client = WebClient(token=slack_bot_token)
print(os.getenv("SLACK_BOT_TOKEN"))

slack_client_id = os.environ["SLACK_CLIENT_ID"]
slack_client_secret = os.environ["SLACK_CLIENT_SECRET"]

@app.route("/slack/events", methods=["POST"])
def slack_events():
    payload = request.json
    if "challenge" in payload:
        return payload["challenge"]  # 返回所需要的`challenge`参数的值
    else:
        # 在這裡處理其它事件
        event = payload.get("event", {})

        # 當收到訊息時
        if payload.get("type") == "event_callback" and event.get("type") == "message":
            channel_id = event.get("channel")
            user = event.get("user")

            # 防止 bot 自己回應自己的訊息
            if user == slack_client_id:
                return jsonify({})

            client.chat_postMessage(channel=channel_id, text="我收到你的訊息了!")

        return jsonify({})


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