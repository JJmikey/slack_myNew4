from flask import Flask, request, jsonify
from flask import Response
from slack_sdk.oauth import AuthorizeUrlGenerator
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

import os 
import requests

import openai

from PIL import Image
import io 
import base64

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


slack_client_id = os.environ["SLACK_CLIENT_ID"]
slack_client_secret = os.environ["SLACK_CLIENT_SECRET"]

vision_only = False

import logging

logging.basicConfig(level=logging.DEBUG)

def download_file(file_id):
      
    # 用Token獲取文件訊息
    FILE_INFO_URL = 'https://slack.com/api/files.info'
    file_info_response = requests.get(
        FILE_INFO_URL, 
        headers={
            'Authorization': 'Bearer {}'.format(slack_bot_token)
        }, 
        params={
            'file': file_id
        })

    # 從response中檢索出文件URL
    file_url = file_info_response.json()['file']['url_private']

    # 使用GET來下載文件
    file_response = requests.get(file_url, headers={'Authorization': 'Bearer {}'.format(slack_bot_token)})

    # 回傳文件內容
    file_content = file_response.content
    
    return file_content


def handle_image(file_content,prompt):
    # 讀取原始圖片數據
    image = Image.open(io.BytesIO(file_content))

    # 縮小圖片
    max_size = (300, 300)
    image.thumbnail(max_size)

    # 將縮小的圖片轉換回二進制數據
    output = io.BytesIO()
    image = image.convert('RGB')
    image.save(output, format='JPEG')
    resized_content = output.getvalue()

    # 將圖像數據轉換為 base64 編碼
    b64_string = base64.b64encode(resized_content).decode()

    # 使用 GPT-4 Vision 處理圖像
    vision_response = openai.ChatCompletion.create(
        model="gpt-4-vision-preview",
        messages=[
        {
            "role": "user",
            "content": [
            {"type": "text", "text": prompt},
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{b64_string}"
                },
            },
            ],
        }
        ]
    )

    response_message = vision_response['choices'][0]['message']['content']
    return response_message



@app.route("/slack/events", methods=["POST"])
def slack_events():
    payload = request.json
    #return payload (截停ERROR BOT時用)

    # Slack 在時限內收不到回應會認為 Request lost，Slack 會再次重複呼叫
    # 會造成重複請求、回應的問題，因此我們可以在 Response Headers 設置 X-Slack-No-Retry: 1 告知 Slack ，就算沒在時限內收到回應也不需 Retry 
    request_headers = request.headers
    headers = {'X-Slack-No-Retry':1}
    # 如果是 Slack Retry 的請求...忽略
    if request_headers and 'X-Slack-Retry-Num' in request_headers:
        return ('OK!', 200, headers)

    if "challenge" in payload:
        return payload["challenge"], 200  # 马上返回所需要的`challenge`参数的值
  
    else:
        # 確保每個事件只被處理一次
        if payload.get("type") == "event_callback":
            event = payload.get("event", {})
            event_type = event.get("type")

            if event_type == "message":
                user = event.get("user")
                prompt = event.get("text")
                channel_id = event.get("channel")
                bot_id = event.get("bot_id")

                # 檢查是否有檔案附件
                files = event.get("files", [])
                if files:
                    vision_only =True
                    for file in files:
                        file_id = file["id"]
                        # 下載檔案
                        file_content = download_file(file_id)
                        # 回應用戶 "收到圖片"
                        client.chat_postMessage(
                        token=slack_bot_token,
                        channel=channel_id,
                        text="收到圖片")

                    response_message=handle_image(file_content,prompt)
                    client.chat_postMessage(channel=channel_id, text=response_message)

                # Ignore bot's own messages
                if user and prompt and channel_id and not bot_id and not vision_only:
                    # when a text message comes in from a user, respond "GOT IT"
                    #client.chat_postMessage(channel=channel_id, text='GOT IT')
                
                    response = openai.ChatCompletion.create(
                            model="gpt-4-1106-preview",
                            messages=[
                                {
                                    "role": "system",
                                    "content": "你是GPT4，你是一個機能理解和模仿人類情緒的虛擬助手。現在的時間是 %s." % local_timestamp
                                },
                                {
                                    "role": "user",
                                    "content": prompt
                                }
                            ]
                        )
                    client.chat_postMessage(channel=channel_id, text=response['choices'][0]['message']['content'])

         

        return {"statusCode": 200}




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