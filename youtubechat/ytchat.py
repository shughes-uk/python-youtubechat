Skip to content
This repository
Search
Pull requests
Issues
Marketplace
Explore
 @Crypti-x
 Sign out
 Watch 0
  Star 0
  Fork 7 Crypti-x/python-youtubechat
forked from shughes-uk/python-youtubechat
 Code  Pull requests 0  Projects 0  Wiki  Settings Insights 
python-youtubechat/youtubechat/ 
ytchat.py
   or cancel
    
 Edit file    Preview changes
1
#!/usr/bin/python
2
# This Python file uses the following encoding: utf-8
3
​
4
import cgi
5
import logging
6
import sys
7
import threading
8
import time
9
from datetime import datetime, timedelta
10
from json import dumps, loads
11
from pprint import pformat
12
​
13
import dateutil.parser
14
import httplib2
15
from oauth2client.file import Storage
16
​
17
PY3 = sys.version_info[0] == 3
18
if PY3:
19
    from urllib.parse import urlencode
20
    from queue import Queue
21
else:
22
    from Queue import Queue
23
    from urllib import urlencode
24
​
25
​
26
class YoutubeLiveChatError(Exception):
27
​
28
    def __init__(self, message, code=None, errors=None):
29
        Exception.__init__(self, message)
30
        self.code = code
31
        self.errors = errors
32
​
33
​
34
def _json_request(http, url, method='GET', headers=None, body=None):
35
    resp, content = http.request(url, method, headers=headers, body=body)
36
    content_type, content_type_params = cgi.parse_header(resp.get('content-type', 'application/json; charset=UTF-8'))
37
    charset = content_type_params.get('charset', 'UTF-8')
38
    data = loads(content.decode(charset))
39
    if 'error' in data:
40
        error = data['error']
41
        raise YoutubeLiveChatError(error['message'], error.get('code'), error.get('errors'))
42
    return resp, data
43
​
44
​
45
def get_datetime_from_string(datestr):
46
    dt = dateutil.parser.parse(datestr)
47
    return dt
48
​
49
def get_top_stream_chat_ids(credential_file):
@Crypti-x
Commit changes

Update ytchat.py

Add an optional extended description…
  Commit directly to the master branch.
  Create a new branch for this commit and start a pull request. Learn more about pull requests.
Commit changes  Cancel
© 2017 GitHub, Inc.
Terms
Privacy
Security
Status
Help
Contact GitHub
API
Training
Shop
Blog
About
