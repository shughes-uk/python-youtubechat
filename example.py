from ytchat import youtube_live_chat, get_liveChatId_for_stream_now
from time import sleep

livechat_id = get_liveChatId_for_stream_now("oauth_creds")
chat_obj = youtube_live_chat("oauth_creds", [livechat_id])


def respond(msgs, chatid):
    for msg in msgs:
        msg.delete()
        chat_obj.send_message("RESPONSE!", chatid)


try:
    chat_obj.start()
    chat_obj.subscribeChatMessage(respond)
    while True:
        sleep(0.1)

finally:
    chat_obj.stop()
