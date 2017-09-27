#!/usr/bin/python
# This Python file uses the following encoding: utf-8

import cgi
import logging
import sys
import threading
import time
from datetime import datetime, timedelta
from json import dumps, loads
from pprint import pformat

import dateutil.parser
import httplib2
from oauth2client.file import Storage

PY3 = sys.version_info[0] == 3
if PY3:
    from urllib.parse import urlencode
    from queue import Queue
else:
    from Queue import Queue
    from urllib import urlencode


class YoutubeLiveChatError(Exception):

    def __init__(self, message, code=None, errors=None):
        Exception.__init__(self, message)
        self.code = code
        self.errors = errors


def _json_request(http, url, method='GET', headers=None, body=None):
    resp, content = http.request(url, method, headers=headers, body=body)
    content_type, content_type_params = cgi.parse_header(resp.get('content-type', 'application/json; charset=UTF-8'))
    charset = content_type_params.get('charset', 'UTF-8')
    data = loads(content.decode(charset))
    if 'error' in data:
        error = data['error']
        raise YoutubeLiveChatError(error['message'], error.get('code'), error.get('errors'))
    return resp, data


def get_datetime_from_string(datestr):
    dt = dateutil.parser.parse(datestr)
    return dt

def get_top_stream_chat_ids(credential_file):
    playlist_id = "PLiCvVJzBupKmEehQ3hnNbbfBjLUyvGlqx"
    storage = Storage(credential_file)
    credentials = storage.get()
    http = credentials.authorize(httplib2.Http())
    url = "https://www.googleapis.com/youtube/v3/playlistItems?"
    params = {'part': 'contentDetails','playlistId':playlist_id}
    params = urlencode(params)
    resp, data = _json_request(http, url + params)
    chatids = []
    for item in data['items']:
        videoid = item['contentDetails']['videoId']
        url = "https://www.googleapis.com/youtube/v3/videos?"
        params = {'part': 'liveStreamingDetails','id': videoid}
        params = urlencode(params)
        response_obj, video_data = _json_request(http, url + params)
        chatId = video_data['items'][0]['liveStreamingDetails']['activeLiveChatId']
        chatids.append(chatId)

    return chatids

def get_live_chat_id_for_stream_now(credential_file):
    storage = Storage(credential_file)
    credentials = storage.get()
    http = credentials.authorize(httplib2.Http())
    url = "https://www.googleapis.com/youtube/v3/liveBroadcasts?"
    params = {'part': 'snippet', 'default': 'true'}
    params = urlencode(params)
    resp, data = _json_request(http, url + params)
    return data['items'][0]['snippet']['liveChatId']


def get_live_chat_id_for_broadcast_id(broadcastId, credential_file):
    storage = Storage(credential_file)
    credentials = storage.get()
    http = credentials.authorize(httplib2.Http())
    url = "https://www.googleapis.com/youtube/v3/liveBroadcasts?"
    params = {'part': 'snippet', 'id': broadcastId}
    params = urlencode(params)
    resp, data = _json_request(http, url + params)
    return data['items'][0]['snippet']['liveChatId']


def channelid_to_name(channelId, http):
    url = "https://www.googleapis.com/youtube/v3/channels?part=snippet&id={0}".format(channelId)
    response, data = _json_request(http, url)
    return data['items'][0]['snippet']['title']


class MessageAuthor(object):

    def __init__(self, json):
        self.is_verified = json['isVerified']
        self.channel_url = json['channelUrl']
        self.profile_image_url = json['profileImageUrl']
        self.channel_id = json['channelId']
        self.display_name = json['displayName']
        self.is_chat_owner = json['isChatOwner']
        self.is_chat_sponsor = json['isChatSponsor']
        self.is_chat_moderator = json['isChatModerator']


class LiveChatMessage(object):

    def __init__(self, http, json):
        self.http = http
        self.json = json
        self.etag = json['etag']
        self.id = json['id']
        snippet = json['snippet']
        self.type = snippet['type']
        self.message_text = snippet['textMessageDetails']['messageText']
        self.display_message = snippet['displayMessage']
        self.has_display_content = snippet['hasDisplayContent']
        self.live_chat_id = snippet['liveChatId']
        self.published_at = get_datetime_from_string(snippet['publishedAt'])
        self.author = MessageAuthor(json['authorDetails'])

    def delete(self):
        url = "https://www.googleapis.com/youtube/v3/liveChat/messages"
        url = url + '?id={0}'.format(self.id)
        resp, content = self.http.request(url, 'DELETE')
    def permaban(self):
        url = "https://www.googleapis.com/youtube/v3/liveChat/bans"
        message = {u'snippet': {u'liveChatId': self.live_chat_id, u'type': 'permanent', "bannedUserDetails": {"channelId": self.author.channel_id}}}
        jsondump = dumps(message)
        url = url + '?part=snippet'
        resp, data = _json_request(self.http,
                                   url,
                                   'POST',
                                   headers={'Content-Type': 'application/json; charset=UTF-8'},
                                   body=jsondump)
        jsonresponse = dumps(data)
        return data['id']
    def tempban(self, timee = 300):
        url = "https://www.googleapis.com/youtube/v3/liveChat/bans"
        message = {u'snippet': {u'liveChatId': self.live_chat_id, u'type': 'temporary', "banDurationSeconds": timee, "bannedUserDetails": {"channelId": self.author.channel_id}}}
        jsondump = dumps(message)
        url = url + '?part=snippet'
        resp, data = _json_request(self.http,
                                   url,
                                   'POST',
                                   headers={'Content-Type': 'application/json; charset=UTF-8'},
                                   body=jsondump)
    def unban(self, id):
        url = "https://www.googleapis.com/youtube/v3/liveChat/bans"
        url = url + '?id=' + id
        content = self.http.request(url, 'DELETE')
    def __repr__(self):
        if PY3:
            return self.display_message
        else:
            return self.display_message.encode("UTF-8")


class LiveChatModerator(object):

    def __init__(self, http, json):
        self.http = http
        self.json = json
        self.etag = json['etag']
        self.id = json['id']
        snippet = json['snippet']
        self.channel_id = snippet['moderatorDetails']['channelId']
        self.channel_url = snippet['moderatorDetails']['channelUrl']
        self.display_name = snippet['moderatorDetails']['displayName']
        self.profile_image_url = snippet['moderatorDetails']['profileImageUrl']

    def delete(self):
        url = "https://www.googleapis.com/youtube/v3/liveChat/moderators"
        url = url + '?id={0}'.format(self.id)
        resp, content = self.http.request(url, 'DELETE')

    def __repr__(self):
        if PY3:
            return self.display_name
        else:
            return self.display_name.encode("UTF-8")


class YoutubeLiveChat(object):

    def __init__(self, credential_filename, livechatIds):
        self.logger = logging.getLogger(name="YoutubeLiveChat")
        self.chat_subscribers = []
        self.thread = threading.Thread(target=self.run)
        self.livechatIds = {}
        self.message_queue = Queue()

        storage = Storage(credential_filename)
        credentials = storage.get()
        self.http = credentials.authorize(httplib2.Http())
        self.livechat_api = LiveChatApi(self.http)

        for chat_id in livechatIds:
            self.livechatIds[chat_id] = {'nextPoll': datetime.now(), 'msg_ids': set(), 'pageToken': None}
            result = self.livechat_api.live_chat_messages_list(chat_id)
            while result['items']:
                pollingIntervalMillis = result['pollingIntervalMillis']
                self.livechatIds[chat_id]['msg_ids'].update(msg['id'] for msg in result['items'])
                self.livechatIds[chat_id]['nextPoll'] = datetime.now() + timedelta(seconds=pollingIntervalMillis / 1000)
                if result['pageInfo']['totalResults'] > result['pageInfo']['resultsPerPage']:
                    self.livechatIds[chat_id]['pageToken'] = result['nextPageToken']
                    time.sleep(result['pollingIntervalMillis'] / 1000)
                    result = self.livechat_api.live_chat_messages_list(chat_id,
                                                                       pageToken=self.livechatIds[chat_id]['pageToken'])
                else:
                    break

        self.logger.debug("Initalized")

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self.run)
        self.thread.daemon = True
        self.thread.start()

    def join(self):
        self.thread.join()

    def stop(self):
        self.running = False
        if self.thread.is_alive():
            self.thread.join()

    def run(self):
        while self.running:
            # send a queued messages
            if not self.message_queue.empty():
                to_send = self.message_queue.get()
                self._send_message(to_send[0], to_send[1])
            # check for messages
            for chat_id in self.livechatIds:
                if self.livechatIds[chat_id]['nextPoll'] < datetime.now():
                    msgcache = self.livechatIds[chat_id]['msg_ids']
                    result = None
                    try:
                        result = self.livechat_api.live_chat_messages_list(
                            chat_id,
                            pageToken=self.livechatIds[chat_id]['pageToken'])
                    except Exception as e:
                        self.logger.warning(e)
                        self.logger.warning("Exception while trying to get yt api")
                    if result:
                        if 'pollingIntervalMillis' not in result:
                            self.logger.warning("Empty result")
                            self.logger.warning(pformat(result))
                            continue
                        pollingIntervalMillis = result['pollingIntervalMillis']
                        while result['items']:
                            latest_messages = {msg['id'] for msg in result['items']}
                            if msgcache:
                                new_messages = latest_messages.difference(msgcache)
                            else:
                                new_messages = latest_messages
                            new_msg_objs = [LiveChatMessage(self.http, json)
                                            for json in result['items'] if json['id'] in new_messages]

                            self.livechatIds[chat_id]['msg_ids'].update(new_messages)
                            nextPoll = datetime.now() + timedelta(seconds=pollingIntervalMillis / 1000)
                            self.livechatIds[chat_id]['nextPoll'] = nextPoll
                            if new_msg_objs:
                                self.logger.debug("New chat messages")
                                self.logger.debug(new_msg_objs)
                                for callback in self.chat_subscribers:
                                    try:
                                        callback(new_msg_objs, chat_id)
                                    except:
                                        msg = "Exception during callback to {0}".format(callback)
                                        self.logger.exception(msg)

                            if result['pageInfo']['totalResults'] > result['pageInfo']['resultsPerPage']:
                                self.livechatIds[chat_id]['pageToken'] = result['nextPageToken']
                                time.sleep(result['pollingIntervalMillis'] / 1000)
                                result = self.livechat_api.live_chat_messages_list(
                                    chat_id,
                                    pageToken=self.livechatIds[chat_id]['pageToken'])
                            else:
                                break

            time.sleep(1)

    def get_moderators(self, livechatId):
        result = self.livechat_api.live_chat_moderators_list(livechatId)
        if result['items']:
            mods = result['items']
            if result['pageInfo']['totalResults'] > result['pageInfo']['resultsPerPage']:
                while result['items']:
                    result = self.livechat_api.live_chat_moderators_list(livechatId, pageToken=result['nextPageToken'])
                    if result['items']:
                        mods.extend(result['items'])
                    else:
                        break
                    if 'nextPageToken' not in result:
                        break
            moderator_objs = [LiveChatModerator(self.http, json) for json in mods]
            return moderator_objs

    def set_moderator(self, livechatId, moderator_channelid):
        message = {u'snippet': {u'liveChatId': livechatId, "moderatorDetails": {"channelId": moderator_channelid}}}
        jsondump = dumps(message)
        return self.livechat_api.live_chat_moderators_insert(jsondump)

    def send_message(self, text, livechatId):
        self.message_queue.put((text, livechatId))

    def _send_message(self, text, livechatId):
        message = {
            u'snippet': {
                u'liveChatId': livechatId,
                "textMessageDetails": {
                    "messageText": text
                },
                "type": "textMessageEvent"
            }
        }

        jsondump = dumps(message)
        response = self.livechat_api.live_chat_messages_insert(jsondump)
        self.logger.debug(pformat(response))
        self.livechatIds[livechatId]['msg_ids'].add(response['id'])

    def subscribe_chat_message(self, callback):
        self.chat_subscribers.append(callback)


class LiveChatApi(object):

    def __init__(self, http):
        self.http = http
        self.logger = logging.getLogger("liveChat_api")

    def get_all_messages(self, livechatId):
        data = self.LiveChatMessages_list(livechatId, maxResults=2000)
        total_items = data['pageInfo']['totalResults']
        pageToken = data['nextPageToken']
        if len(data['items']) < total_items:
            time.sleep(data['pollingIntervalMillis'] / 1000)
            while len(data['items']) < total_items:
                other_data = self.LiveChatMessages_list(livechatId, maxResults=2000, pageToken=pageToken)
                if not other_data['items']:
                    break
                else:
                    data['items'].extend(other_data['items'])
                    pageToken = other_data['nextPageToken']
                    time.sleep(other_data['pollingIntervalMillis'] / 1000)
        return data

    def live_chat_moderators_list(self, livechatId, part='snippet', maxResults=5, pageToken=None):
        url = 'https://www.googleapis.com/youtube/v3/liveChat/moderators'
        url = url + '?liveChatId={0}'.format(livechatId)
        if pageToken:
            url = url + '&pageToken={0}'.format(pageToken)
        url = url + '&part={0}'.format(part)
        url = url + '&maxResults={0}'.format(maxResults)
        resp, data = _json_request(self.http, url)
        resp, content = self.http.request(url, 'GET')
        data = loads(content.decode("UTF-8"))
        return data

    def live_chat_moderators_insert(self, liveChatId, liveChatModerator):
        url = 'https://www.googleapis.com/youtube/v3/liveChat/messages'
        url = url + '?part=snippet'
        resp, data = _json_request(self.http,
                                   url,
                                   'POST',
                                   headers={'Content-Type': 'application/json; charset=UTF-8'},
                                   body=liveChatModerator)
        return data

    def live_chat_messages_list(self,
                                livechatId,
                                part='snippet,authorDetails',
                                maxResults=200,
                                pageToken=None,
                                profileImageSize=None):
        url = 'https://www.googleapis.com/youtube/v3/liveChat/messages'
        url = url + '?liveChatId={0}'.format(livechatId)
        if pageToken:
            url = url + '&pageToken={0}'.format(pageToken)
        if profileImageSize:
            url = url + '&profileImageSize={0}'.format(profileImageSize)
        url = url + '&part={0}'.format(part)
        url = url + '&maxResults={0}'.format(maxResults)
        resp, data = _json_request(self.http, url)
        return data

    def live_chat_messages_insert(self, liveChatMessage):
        url = 'https://www.googleapis.com/youtube/v3/liveChat/messages'
        url = url + '?part=snippet'
        resp, data = _json_request(self.http,
                                   url,
                                   'POST',
                                   headers={'Content-Type': 'application/json; charset=UTF-8'},
                                   body=liveChatMessage)
        self.logger.debug(pformat(resp))
        return data

    def live_chat_message_delete(self, idstring):
        "DELETE https://www.googleapis.com/youtube/v3/liveChat/messages"
