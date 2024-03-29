from flask import Flask, request, jsonify
from flask import Response
from slack_sdk.oauth import AuthorizeUrlGenerator
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

import os 
import requests #only required when using proxy
from requests.exceptions import HTTPError

import json
from json import JSONDecodeError

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

                # Set vision_only to False initially
                vision_only = False 

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
                
                    # 获取历史消息,限制历史消息的数目，并将历史消息添加到列表
                    history = client.conversations_history(
                        channel=channel_id,
                        limit=4
                    )
                    # 创建消息列表
                    messages = []                  
                                        
                                      
                    # 遍歷訊息歷史
                    for msg in history['messages']:
                        if msg['type'] == 'message' and 'subtype' not in msg:
                            # 從 'blocks' 中提取文字
                            text = ''
                            for block in msg.get('blocks', []):
                                for element in block.get('elements', []):
                                    for inner_elem in element.get('elements', []):
                                        if inner_elem['type'] == 'text':
                                            text += inner_elem.get('text', '')
                            # 根據 'bot_id' 是否存在來判定 'role'
                            role = 'assistant' if 'bot_id' in msg else 'user'
                            # 創建訊息 dictionary
                            content_msg = {
                                "role": role,
                                "content": text
                            }
                        # 將訊息加入訊息列表的最前面                        
                        messages.insert(0, content_msg)


                    # 創建一個結合所有訊息的單一字符串
                    text_history = "\n".join([f"{msg['role']}: {msg['content']}" for msg in messages])

                    # 創建用戶訊息 dictionary
                    user_msg = [
                        {
                            "role": "system",
                            "content": "你是GPT4，你是一個機能理解和模仿人類情緒的虛擬助手。現在的時間是 %s." % local_timestamp
                        },
                        {
                        "role": 'user',
                        "content": prompt 
                    }
                    ]            
                    
                   
                    # 將用戶訊息添加到"消息历史记录"字串的最後
                    for msg in user_msg:
                        text_history += "\n{role}: {content}".format(**msg)


                    # 分裂 text_history 成基於換行符的 list
                    split_history = text_history.split("\n")

                    # 為每條訊息創建一個dictionary
                    message_dicts = []
                    for message in split_history:
                        # 分裂 message 成 'role' 和 'content'
                        role, content = message.split(': ', 1) 
                        message_dict = {
                            "role": role.strip(),
                            "content": content.strip()
                        }
                        # 將 dictionary 添加至 message_dicts list
                        message_dicts.append(message_dict)

                    #PROXY
                    #text = test(messages)
                
                    #using OPENAI API
                    response = openai.ChatCompletion.create(
                            model="gpt-4-1106-preview",
                            messages=message_dicts
                        )
                    
                    text=response['choices'][0]['message']['content']
                    client.chat_postMessage(channel=channel_id, text=text)

                    #channel history -- extract and write to file (need to develop this feature)
                    #history = client.conversations_history(
                    #    channel=channel_id,
                    #    oldest='1711382400',
                    #    #latest='1711516575'
                    #)

                    # 检查是否成功获取历史信息
                    #if history['ok']:
                    #    messages = history['messages']

                        # 遍历消息并生成一个消息列表字符串
                    #    messages_text = ""
                    #    for msg in messages:
                    #        messages_text += f"User: {msg['user']} Text: {msg['text']}\n"

                        #if messages_text.strip() == "":
                            #client.chat_postMessage(channel=channel_id, text="No messages were found in the given time range.")
                        #else:
                            #client.chat_postMessage(channel=channel_id, text=messages_text)
         

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


@app.route("/test", methods=["POST"])
def test(messages):
    # Get user's message from the request data (using postman)
    #user_message = request.json['content']

    shuttle_url = 'https://api.shuttleai.app/v1/chat/completions' 
    shuttle_key = 'Bearer shuttle-8619fc3825f9175a8ee5'  
    shuttle_model = "gpt-4-0613"
    oxy_url = 'https://app.oxyapi.uk/v1/chat/completions'
    oxy_key = 'Bearer oxy-mWs1TuolqoT44Cmfj3ixE8FHRcqANOXEVn8abrQ24GBpo'
    oxy_model = "gpt-3.5-turbo"
    url = shuttle_url
    headers = {
        'Content-Type': 'application/json',
        'Authorization': shuttle_key,
          
    }

    data = {
        "model": shuttle_model,
        "messages": [{"role": "user", "content": messages}],
        "temperature": 0.7
    }

    try:
        response = requests.post(url, headers=headers, json=data)

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
            json_response = response.json()
            text = json_response['choices'][0]['message']['content']
            return text
            return response.json()  #for using postman
           
        except JSONDecodeError:
            return "Error: Response could not be parsed as JSON."
    else:
        return "Error: Received status code " + str(response.status_code)


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080))) #for deploy on vercel