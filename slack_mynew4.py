from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

import os 

token = os.getenv("Bot_User_OAuth_Token")
client = WebClient(token=token)

try:
    response = client.chat_postMessage(channel="#channel-name", text="Hello, world!")
except SlackApiError as e:
    print(f"Error: {e.response['error']}")  