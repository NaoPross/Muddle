#!/usr/bin/env python3
import requests
import logging
import dataclasses

from typing import List

log = logging.getLogger("muddle.moodle")


def get_token(url, user, password):
    token_url = f"{url}/login/token.php"
    data = {
        "username": user,
        "password": password,
        "service": "moodle_mobile_app"
    }
    log.debug(f"requesting token with POST to {url} with DATA {data}")
    return requests.post(token_url, data=data)


class RestApi:
    """
    Magic REST API wrapper (ab)using lambdas
    """
    def __init__(self, instance_url, token=None):
        self._url = instance_url
        if token:
            self._token = token

    def __getattr__(self, key):
        return lambda **kwargs: RestApi._call(self._url, self._token, str(key), **kwargs)

    def _call(self, function, **kwargs):
        return RestApi._call(self._url, self._token, kwargs)

    @staticmethod
    def _call(url, token, function, **kwargs):
        api_url = f"{url}/webservice/rest/server.php?moodlewsrestformat=json"
        data = {"wstoken": token, "wsfunction": function}
        for k, v in kwargs.items():
            data[str(k)] = v

        log.debug(f"calling api with POST to {api_url} with DATA {data}")
        try:
            req = requests.post(api_url, data=data)
            req.raise_for_status()
        except requests.HTTPError:
            log.warn("Error code returned by HTTP(s) request")
        except (requests.ConnectionError, requests.Timeout, requests.ReadTimeout) as e:
            log.error(f"Failed to connect for POST request:\n{str(e)}")
        finally:
            return req


class MoodleInstance:
    """
    A more frendly API that wraps around the raw RestApi
    """
    def __init__(self, url, token):
        self.api = RestApi(url, token)
        self.userid = None

    def get_userid(self):
        if self.userid is None:
            req = self.api.core_webservice_get_site_info()
            self.userid = req.json()["userid"]

        return self.userid

    def get_enrolled_courses(self):
        req = self.api.core_enrol_get_users_courses(userid=self.get_userid())
        for c in req.json():
            yield Course._fromdict(c)


# A bare minimum impl of Moodle SCHEMA
# Beware that lots of parameters have been omitted

class SchemaObj:
    @classmethod
    def _fromdict(cls, d):
        """
        Creates a schema object from a dictionary, if the dictionary contains
        keys that are not present in the schema object they will be ignored
        """
        if cls is SchemaObj:
            raise TypeError("Must be used in a subclass")

        fields = [f.name for f in dataclasses.fields(cls)]
        filtered = {k: v for k, v in d.items() if k in fields}

        return cls(**filtered)


@dataclasses.dataclass
class Course(SchemaObj):
    """
    A course, pretty self explanatory
    https://www.examulator.com/er/output/tables/course.html
    """
    id: int
    shortname: str
    fullname: str
    summary: str
    startdate: int
    enddate: int

    def get_sections(self, api):
        req = api.core_course_get_contents(courseid=self.id)
        for s in req.json():
            # rest api response does not contain course id
            s["course"] = self.id
            yield Section._fromdict(s)


@dataclasses.dataclass
class Section(SchemaObj):
    """
    Sections of a course
    https://www.examulator.com/er/output/tables/course_sections.html
    """
    id: int
    course: int
    section: int
    name: str
    summary: str
    visible: bool

    modules: List

    def get_modules(self):
        for m in self.modules:
            yield Module._fromdict(m)


@dataclasses.dataclass
class Module(SchemaObj):
    """
    Modules of a Course, they are grouped in sections
    https://www.examulator.com/er/output/tables/course_modules.html
    """
    id: int
    name: str


@dataclasses.dataclass
class File(SchemaObj):
    filename: str
    fileurl: str


@dataclasses.dataclass
class Folder(SchemaObj):
    pass


@dataclasses.dataclass
class ExternalLink(SchemaObj):
    pass


class ApiHelper:
    def __init__(self, api):
        self.api = api

    def get_userid(self):
        req = self.api.core_webservice_get_site_info()
        if req:
            return req.json()["userid"]
        else:
            return None

    def get_file(self, url, local_path):
        with requests.post(url, data={"token": self.api._token}, stream=True) as r:
            r.raise_for_status()
            with open(local_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
