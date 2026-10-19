"""Fake HTTP transport for the Cloud Functions API and the upload URL."""

import json

from google.auth.credentials import AnonymousCredentials
from googleapiclient import discovery
from googleapiclient.http import HttpMockSequence

_real_build = discovery.build
JSON = {"content-type": "application/json"}


def response(body, status=200):
    return ({**JSON, "status": str(status)}, json.dumps(body))


class FakeApi:
    """Replaces `discovery.build` with a client that talks to canned responses."""

    def __init__(self, responses):
        self.http = HttpMockSequence(responses)

    def build(self, serviceName, version, credentials=None, **kwargs):
        return _real_build(serviceName, version, http=self.http, **kwargs)


class FakePut:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text
        self.calls = []

    @property
    def ok(self):
        return self.status_code < 400

    def __call__(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self


def anonymous_credentials():
    return AnonymousCredentials()
