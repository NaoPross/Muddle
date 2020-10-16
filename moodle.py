#!/usr/bin/env python3
import requests
import logging

log = logging.getLogger("muddle.moodle")

#
# magic moodle api wrapper
#
def request_token(url, user, password):
    token_url = f"{url}/login/token.php"
    data = { "username": user, "password": password, "service": "moodle_mobile_app" }
    log.debug(f"requesting token with POST to {api_url} with DATA {data}")
    return requests.post(token_url, data=data)

def api_call(url, token, function, **kwargs):
    api_url = f"{url}/webservice/rest/server.php?moodlewsrestformat=json"
    data = { "wstoken": token, "wsfunction": function }
    for k, v in kwargs.items():
        data[str(k)] = v

    log.debug(f"calling api with POST to {api_url} with DATA {data}")
    return requests.post(api_url, data=data)

class RestApi:
    def __init__(self, instance_url, token):
        self._url = instance_url
        self._token = token

    def __getattr__(self, key):
        return lambda **kwargs: api_call(self._url, self._token, str(key), **kwargs)

class ApiHelper:
    def __init__(self, api):
        self.api = api

    def get_userid(self):
        return self.api.core_webservice_get_site_info().json()["userid"]

    def get_file(self, url, local_path):
        with requests.post(url, data={"token": self.api._token}, stream=True) as r:
            r.raise_for_status()
            with open(local_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
