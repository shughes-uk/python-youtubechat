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
from HTMLParser import HTMLParser

html_parser = HTMLParser()


def get_datetime_from_string(datestr):
    dt = dateutil.parser.parse(datestr)
    return dt


def get_live_chat_id_for_stream_now(credential_file):
    storage = Storage("oauth_creds")
    credentials = storage.get()
    http = credentials.authorize(httplib2.Http())
    url = "https://www.googleapis.com/youtube/v3/liveBroadcasts?"
    params = {'part': 'snippet', 'default': 'true'}
    params = urllib.urlencode(params)
    resp, content = http.request(url + params, 'GET')
    data = loads(content)
    return data['items'][0]['snippet']['liveChatId']


def get_live_chat_id_for_broadcast_id(broadcastId, credential_file):
    storage = Storage("oauth_creds")
    credentials = storage.get()
    http = credentials.authorize(httplib2.Http())
    url = "https://www.googleapis.com/youtube/v3/liveBroadcasts?"
    params = {'part': 'snippet', 'id': broadcastId}
    params = urllib.urlencode(params)
    resp, content = http.request(url + params, 'GET')
    data = loads(content)
    return data['items'][0]['snippet']['liveChatId']


def channelid_to_name(channelId, http):
    url = "https://www.googleapis.com/youtube/v3/channels?part=snippet&id={0}".format(channelId)
    response, content = http.request(url, "GET")
    data = loads(content)
    return data['items'][0]['snippet']['title']


class LiveChatMessage(object):

    def __init__(self, http, json):
        self.http = http
        self.json = json
        self.etag = json['etag']
        self.id = json['id']
        snippet = json['snippet']
        self.type = snippet['type']
        self.message_text = html_parser.unescape(snippet['textMessageDetails']['messageText'].encode('UTF-8'))
        self.display_message = html_parser.unescape(snippet['displayMessage'].encode('UTF-8'))
        self.has_display_content = snippet['hasDisplayContent']
        self.live_chat_id = snippet['liveChatId']
        self.author_channel_id = snippet['authorChannelId']
        self.author_channel_name = channelid_to_name(self.author_channel_id, http)
        self.published_at = get_datetime_from_string(snippet['publishedAt'])

    def delete(self):
        url = "https://www.googleapis.com/youtube/v3/liveChat/messages"
        url = url + '?id={0}'.format(self.id)
        resp, content = self.http.request(url, 'DELETE')

    def __repr__(self):
        return self.display_message


class YoutubeLiveChat(object):

    def __init__(self, credential_filename, livechatIds):
        self.logger = logging.getLogger(name="YoutubeLiveChat")
        self.chat_subscribers = []
        self.thread = threading.Thread(target=self.run)
        self.livechatIds = {}

        storage = Storage(credential_filename)
        credentials = storage.get()
        self.http = credentials.authorize(httplib2.Http())
        self.livechat_api = LiveChatApi(self.http)

        for chat_id in livechatIds:
            self.livechatIds[chat_id] = {'nextPoll': datetime.now(), 'msg_ids': None, 'pageToken': None}
            result = self.livechat_api.live_chat_messages_list(chat_id)
            while result['items']:
                pollingIntervalMillis = result['pollingIntervalMillis']
                self.livechatIds[chat_id]['msg_ids'] = {msg['id'] for msg in result['items']}
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

    def stop(self):
        self.running = False
        if self.thread.is_alive():
            self.thread.join

    def run(self):
        while self.running:
            for chat_id in self.livechatIds:
                if self.livechatIds[chat_id]['nextPoll'] < datetime.now():
                    msgcache = self.livechatIds[chat_id]['msg_ids']

                    result = self.livechat_api.live_chat_messages_list(chat_id,
                                                                       pageToken=self.livechatIds[chat_id]['pageToken'])
                    pollingIntervalMillis = result['pollingIntervalMillis']
                    while result['items']:
                        latest_messages = {msg['id'] for msg in result['items']}
                        new_messages = latest_messages.difference(msgcache)
                        new_msg_objs = [LiveChatMessage(self.http, json) for json in result['items']
                                        if json['id'] in new_messages]

                        self.livechatIds[chat_id]['msg_ids'].update(new_messages)
                        nextPoll = datetime.now() + timedelta(seconds=pollingIntervalMillis / 1000)
                        self.livechatIds[chat_id]['nextPoll'] = nextPoll
                        if new_msg_objs:
                            self.logger.debug("New chat messages")
                            self.logger.debug(new_msg_objs)
                            for callback in self.chat_subscribers:
                                callback(new_msg_objs, chat_id)

                        if result['pageInfo']['totalResults'] > result['pageInfo']['resultsPerPage']:
                            self.livechatIds[chat_id]['pageToken'] = result['nextPageToken']
                            time.sleep(result['pollingIntervalMillis'] / 1000)
                            result = self.livechat_api.live_chat_messages_list(
                                chat_id,
                                pageToken=self.livechatIds[chat_id]['pageToken'])
                        else:
                            break

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
        response = self.livechat_api.live_chat_messages_insert(jsondump)
        self.livechatIds[livechat_id]['msg_ids'].add(response['id'])

    def subscribe_chat_message(self, callback):
        self.chat_subscribers.append(callback)


class LiveChatApi(object):

    def __init__(self, http):
        self.http = http
        self.logger = logging.getLogger("liveChat_api")

    def get_all_messages(self, livechatId):
        data = self.LiveChatMessages_list(livechatId, 50)
        total_items = data['pageInfo']['totalResults']
        pageToken = data['nextPageToken']
        if len(data['items']) < total_items:
            time.sleep(data['pollingIntervalMillis'] / 1000)
            while len(data['items']) < total_items:
                other_data = self.LiveChatMessages_list(livechatId, 50, pageToken)
                if not other_data['items']:
                    break
                else:
                    data['items'].extend(other_data['items'])
                    pageToken = other_data['nextPageToken']
                    time.sleep(other_data['pollingIntervalMillis'] / 1000)
        return data

    def live_chat_messages_list(self, livechatId, maxResults=25, pageToken=None):
        url = 'https://www.googleapis.com/youtube/v3/liveChat/messages'
        url = url + '?liveChatId={0}'.format(livechatId)
        if pageToken:
            url = url + '&pageToken={0}'.format(pageToken)
        url = url + '&part=snippet'
        url = url + '&maxResults={0}'.format(maxResults)
        resp, content = self.http.request(url, 'GET')
        data = loads(content)
        return data

    def live_chat_messages_insert(self, liveChatMessage):
        url = 'https://www.googleapis.com/youtube/v3/liveChat/messages'
        url = url + '?part=snippet'
        resp, content = self.http.request(url,
                                          'POST',
                                          headers={'Content-Type': 'application/json; charset=UTF-8'},
                                          body=liveChatMessage)
        data = loads(content)
        return data

    def live_chat_message_delete(self, idstring):
        "DELETE https://www.googleapis.com/youtube/v3/liveChat/messages"
