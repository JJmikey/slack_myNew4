from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

client = WebClient(token="你的Bot User OAuth Token")

try:
    response = client.chat_postMessage(channel="#channel-name", text="Hello, world!")
except SlackApiError as e:
    print(f"Error: {e.response['error']}")