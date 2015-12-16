#!/usr/bin/python

import httplib2
import urllib
import logging
import time
from json import loads, dumps
import dateutil.parser
from oauth2client.file import Storage
from datetime import datetime, timedelta
import threading
from pprint import pformat


def get_datetime_from_string(datestr):
    dt = dateutil.parser.parse(datestr)
    return dt


def get_liveChatId_for_stream_now(credential_file):
    storage = Storage("oauth_creds")
    credentials = storage.get()
    http = credentials.authorize(httplib2.Http())
    url = "https://www.googleapis.com/youtube/v3/liveBroadcasts?"
    params = {'part': 'snippet', 'default': 'true'}
    params = urllib.urlencode(params)
    resp, content = http.request(url + params, 'GET')
    data = loads(content)
    return data['items'][0]['snippet']['liveChatId']


def get_liveChatId_for_broadcastId(broadcastId, credential_file):
    storage = Storage("oauth_creds")
    credentials = storage.get()
    http = credentials.authorize(httplib2.Http())
    url = "https://www.googleapis.com/youtube/v3/liveBroadcasts?"
    params = {'part': 'snippet', 'id': broadcastId}
    params = urllib.urlencode(params)
    resp, content = http.request(url + params, 'GET')
    data = loads(content)
    return data['items'][0]['snippet']['liveChatId']


def resolveChannelIdToName(channelId, http):
    url = "https://www.googleapis.com/youtube/v3/channels?part=snippet&id={0}".format(channelId)
    response, content = http.request(url, "GET")
    data = loads(content)
    return data['items'][0]['snippet']['title']


class livechatMessage(object):

    def __init__(self, http, json=None):
        self.http = http
        if json:
            self.json = json
            self.etag = json['etag']
            self.id = json['id']
            snippet = json['snippet']
            self.type = snippet['type']
            self.messageText = snippet['textMessageDetails']['messageText'].encode('UTF-8')
            self.displayMessage = snippet['displayMessage'].encode('UTF-8')
            self.hasDisplayContent = snippet['hasDisplayContent']
            self.liveChatId = snippet['liveChatId']
            self.authorChannelId = snippet['authorChannelId']
            self.authorChannelName = resolveChannelIdToName(self.authorChannelId, http)
            self.publishedAt = get_datetime_from_string(snippet['publishedAt'])

    def delete(self):
        url = "https://www.googleapis.com/youtube/v3/liveChat/messages"
        url = url + '?id={0}'.format(self.id)
        resp, content = self.http.request(url, 'DELETE')

    def __repr__(self):
        return self.displayMessage


class youtube_live_chat(object):

    def __init__(self, credential_filename, livechatIds):
        self.logger = logging.getLogger(name="youtube_live_chat")
        self.chat_subscribers = []
        self.thread = threading.Thread(target=self.run)
        self.livechatIds = {}

        storage = Storage(credential_filename)
        credentials = storage.get()
        self.http = credentials.authorize(httplib2.Http())
        self.liveChat_api = liveChat_api(self.http)

        for chat_id in livechatIds:
            self.livechatIds[chat_id] = {'nextPoll': datetime.now(), 'msg_ids': None}
            result = self.liveChat_api.LiveChatMessages_list(chat_id)
            pollingIntervalMillis = result['pollingIntervalMillis']
            self.livechatIds[chat_id]['msg_ids'] = {msg['id'] for msg in result['items']}
            self.livechatIds[chat_id]['nextPoll'] = datetime.now() + timedelta(seconds=pollingIntervalMillis / 1000)
        self.logger.debug("Initalized")

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self.run)
        self.thread.daemon = True
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread.is_alive():
            self.thread.join

    def run(self):
        while self.running:
            for chat_id in self.livechatIds:
                if self.livechatIds[chat_id]['nextPoll'] < datetime.now():
                    msgcache = self.livechatIds[chat_id]['msg_ids']

                    result = self.liveChat_api.LiveChatMessages_list(chat_id)
                    pollingIntervalMillis = result['pollingIntervalMillis']
                    latest_messages = {msg['id'] for msg in result['items']}
                    new_messages = latest_messages.difference(msgcache)

                    new_msg_objs = [livechatMessage(self.http, json) for json in result['items']
                                    if json['id'] in new_messages]

                    self.livechatIds[chat_id]['msg_ids'].update(new_messages)
                    nextPoll = datetime.now() + timedelta(seconds=pollingIntervalMillis / 1000)
                    self.livechatIds[chat_id]['nextPoll'] = nextPoll
                    if new_msg_objs:
                        self.logger.debug("New chat messages")
                        self.logger.debug(new_msg_objs)
                        for callback in self.chat_subscribers:
                            callback(new_msg_objs, chat_id)
            time.sleep(1)

    def send_message(self, text, livechat_id):
        message = {
            u'snippet': {
                u'liveChatId': livechat_id,
                "textMessageDetails": {
                    "messageText": text
                },
                "type": "textMessageEvent"
            }
        }

        jsondump = dumps(message)
        response = self.liveChat_api.LiveChatMessages_insert(jsondump)
        self.livechatIds[livechat_id]['msg_ids'].add(response['id'])

    def subscribeChatMessage(self, callback):
        self.chat_subscribers.append(callback)


class liveChat_api(object):

    def __init__(self, http):
        self.http = http

    def LiveChatMessages_list(self, livechatId, maxResults=25, pageToken=None):
        url = 'https://www.googleapis.com/youtube/v3/liveChat/messages'
        url = url + '?liveChatId={0}'.format(livechatId)
        url = url + '&part=snippet'
        if pageToken:
            url = url + '&pageToken={0}'.format(pageToken)
        resp, content = self.http.request(url, 'GET')
        data = loads(content)
        return data

    def LiveChatMessages_insert(self, liveChatMessage):
        url = 'https://www.googleapis.com/youtube/v3/liveChat/messages'
        url = url + '?part=snippet'
        resp, content = self.http.request(url,
                                          'POST',
                                          headers={'Content-Type': 'application/json; charset=UTF-8'},
                                          body=liveChatMessage)
        data = loads(content)
        return data

    def LiveChatMessages_delete(self, idstring):
        "DELETE https://www.googleapis.com/youtube/v3/liveChat/messages"
