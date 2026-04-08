import unittest
from types import SimpleNamespace
from unittest import mock

import inesdata


class _FakeSession:
    def __init__(self, login_response, edition_response):
        self._login_response = login_response
        self._edition_response = edition_response
        self.post_calls = []

    def get(self, url, timeout=20, allow_redirects=True):
        if url.endswith("/edition/login"):
            return self._login_response
        if url.endswith("/edition"):
            return self._edition_response
        raise AssertionError(f"Unexpected GET URL: {url}")

    def post(self, url, data=None, timeout=20, allow_redirects=True):
        self.post_calls.append((url, data))
        return SimpleNamespace(status_code=200, text="", url=url)


class OntologyHubCleanupGuardsTests(unittest.TestCase):
    def test_response_looks_broken_when_hidden_500_is_rendered_with_status_200(self):
        response = SimpleNamespace(
            status_code=200,
            text="<html><h1>500 - Oops! something went wrong - 500</h1></html>",
        )

        self.assertTrue(inesdata._ontology_hub_response_looks_broken(response))

    def test_response_looks_broken_when_stacktrace_mentions_null_agent_name(self):
        response = SimpleNamespace(
            status_code=200,
            text="TypeError: /app/app/views/edition.jade:153 Cannot read properties of null (reading 'name')",
        )

        self.assertTrue(inesdata._ontology_hub_response_looks_broken(response))

    def test_session_login_rejects_authenticated_broken_edition_page(self):
        runtime = {
            "baseUrl": "http://ontology-hub-demo.dev.ds.dataspaceunit.upm",
            "adminEmail": "admin@gmail.com",
            "adminPassword": "admin1234",
        }
        login_response = SimpleNamespace(
            status_code=200,
            text="<input type='hidden' name='_csrf' value='token'>",
            url=f"{runtime['baseUrl']}/edition/login",
        )
        edition_response = SimpleNamespace(
            status_code=200,
            text="<h1>500 - Oops! something went wrong - 500</h1>",
            url=f"{runtime['baseUrl']}/edition",
        )
        session = _FakeSession(login_response, edition_response)

        with mock.patch("inesdata.requests.Session", return_value=session):
            authenticated = inesdata._ontology_hub_session_login(runtime)

        self.assertIsNone(authenticated)


if __name__ == "__main__":
    unittest.main()
