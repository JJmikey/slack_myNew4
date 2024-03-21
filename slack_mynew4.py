from flask import Flask, request, jsonify
from slack_sdk.oauth import AuthorizeUrlGenerator
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

import os 
import requests #only required when using proxy
from requests.exceptions import HTTPError

import json
from json import JSONDecodeError
import openai

from datetime import datetime
from pytz import timezone



app = Flask(__name__)

hongkong_tz = timezone('Asia/Hong_Kong')
hongkong_time = datetime.now(hongkong_tz)
local_timestamp = hongkong_time.isoformat(timespec='seconds')

# 你的 OpenAI API key
openai.api_key = os.getenv("OPENAI_API_KEY")

slack_bot_token = os.environ["SLACK_BOT_TOKEN"] # 用以調用 Slack API 
client = WebClient(token=slack_bot_token)
print(os.getenv("SLACK_BOT_TOKEN"))

slack_client_id = os.environ["SLACK_CLIENT_ID"]
slack_client_secret = os.environ["SLACK_CLIENT_SECRET"]

import logging

logging.basicConfig(level=logging.info)



@app.route("/slack/events", methods=["POST"])
def slack_events():
    payload = request.json
    if "challenge" in payload:
        return payload["challenge"], 200  # 马上返回所需要的`challenge`参数的值
    else:
        # 在這裡處理其它事件
        event = payload.get("event", {})

        # 當收到訊息時
        if payload.get("type") == "event_callback" and event.get("type") == "message" and "bot_id" not in event:
            try:    
                channel_id = event.get("channel")

                # Use reverse proxy API to generate a message
                prompt = event.get('text')
                logging.debug("Received prompt: %s", prompt)

                url = 'https://app.oxyapi.uk/v1/chat/completions'
                headers = {
                    'Content-Type': 'application/json',
                    'Authorization': 'Bearer '+os.environ.get('OXY_API_KEY'),
                }
                data = json.dumps({
                        "model": "gpt-3.5-turbo",
                        "messages": [{"role": "user", "content": "你幾時退休"}],
                        "temperature": 0.7
                        })

                # send a post request
                response = requests.post(url, headers=headers, data=data)

                logging.info("Response status code: %s", response.status_code)
                logging.info("Response headers: %s", response.headers)
                logging.info("Response text: %s", response.text)

                if response.text:
                    response_json = response.json()
                else:
                    logging.error("Empty response received.")
                    return {"statusCode": 500, "body": "Empty response received."}, 500
                        
                logging.debug("GPT-4 response: %s", response_json)

                if 'choices' in response_json and len(response_json['choices']) > 0:
                    # extract the 'content' from the response
                    response_message = response_json['choices'][0]['message']['content']
                else:
                    response_message = "GPT-4 error"



                client.chat_postMessage(channel=channel_id, text=response_message)

                return {"statusCode": 200}

            except Exception as e:
                logging.error("Exception occurred", exc_info=True)
                return {"statusCode": 500, "body": "An error occurred: " + str(e)}
        

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

@app.route("/test", methods=["POST"])
def test():
    url = 'https://app.oxyapi.uk/v1/chat/completions'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer '+os.environ.get('OXY_API_KEY'),
    }

    data = {
        "model": "gpt-3.5-turbo",
        "messages": [{"role": "user", "content": "講一個3個字的故事"}],
        "temperature": 0.7
    }

    try:
        response = requests.post(url, headers=headers, data=json.dumps(data))

        # If the response was successful, no Exception will be raised
        response.raise_for_status()
    except HTTPError as http_err:
        print(f'HTTP error occurred: {http_err}''')  # Python 3.6
    except Exception as err:
        print(f'其他錯誤發生: {err}')  # Python 3.6
    else:
        print('成功')

    if response.status_code == 200: 
        try:
            return response.json()
        except JSONDecodeError:
            return "Error: Response could not be parsed as JSON."
    else:
        return "Error: Received status code " + str(response.status_code)



    


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080))) #for deploy on vercel