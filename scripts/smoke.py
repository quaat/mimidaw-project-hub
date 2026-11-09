#!/usr/bin/env python3
"""Non-destructive HTTP smoke test for a running Hub. Uses stdlib only."""
import getpass
import http.cookiejar
import json
import os
import sys
import urllib.error
import urllib.request

base = (sys.argv[1] if len(sys.argv)>1 else 'http://127.0.0.1:8090').rstrip('/')
password = os.environ.get('HUB_ADMIN_PASSWORD') or getpass.getpass('Hub password: ')
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

def request(path, method='GET', data=None, csrf=None):
    payload = json.dumps(data).encode() if data is not None else None
    headers = {'Content-Type': 'application/json'} if payload else {}
    if csrf: headers['X-CSRF-Token'] = csrf
    with opener.open(urllib.request.Request(base+path,data=payload,headers=headers,method=method),timeout=10) as response:
        return json.load(response)

assert request('/api/v1/health')['ok']
auth = request('/api/v1/session/login','POST',{'password':password})
assert auth['authenticated']
assert request('/api/v1/session')['authenticated']
projects = request('/api/v1/projects?limit=5')
assert isinstance(projects['items'],list)
print('PASS: health, login, authenticated project listing; projects:',projects['total'])
print('UI:',base+'/')
