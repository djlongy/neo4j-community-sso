"""Verify SSO admission, HTTP queries and Bolt WebSockets against a disposable test deployment."""
import argparse
import base64
import http.cookiejar
import json
import os
from pathlib import Path
import socket
import ssl
import struct
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

ROOT = Path(__file__).resolve().parent.parent
BASE = "http://localhost:7476"
ISSUER = "http://localhost:9480/realms/neo4j"
CA_FILE = None
USERNAME = "demo"
DENIED_USERNAME = "outsider"
PASSWORD = None


def demo_password():
    p = ROOT / ".env.demo"
    if p.exists():
        for line in p.read_text().splitlines():
            if line.startswith("DEMO_PASSWORD="):
                return line.split("=", 1)[1]
    return None


class LoginForm(HTMLParser):
    def __init__(self):
        super().__init__()
        self.action = None
        self.fields = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form" and attrs.get("id") == "kc-form-login":
            self.action = attrs["action"]
        if tag == "input" and attrs.get("type") == "hidden" and "name" in attrs:
            self.fields[attrs["name"]] = attrs.get("value", "")


def client():
    jar = http.cookiejar.CookieJar(policy=LocalDemoCookiePolicy())
    context = ssl.create_default_context(cafile=CA_FILE)
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar),
        urllib.request.HTTPSHandler(context=context),
    )
    return opener, jar


class LocalDemoCookiePolicy(http.cookiejar.DefaultCookiePolicy):
    def return_ok_secure(self, cookie, request):
        # Browsers treat HTTP localhost as trustworthy; stdlib CookieJar does not.
        if request.type == "http" and urllib.parse.urlsplit(request.full_url).hostname == "localhost":
            return True
        return super().return_ok_secure(cookie, request)


def login(username, password):
    opener, jar = client()
    with opener.open(BASE + "/browser/", timeout=15) as response:
        form = LoginForm()
        form.feed(response.read().decode())
    assert form.action, "Keycloak login form not found"
    action = urllib.parse.urlsplit(form.action)
    issuer = urllib.parse.urlsplit(ISSUER)
    assert (action.scheme, action.netloc) == (issuer.scheme, issuer.netloc)
    form.fields.update(username=username, password=password)
    request = urllib.request.Request(form.action, data=urllib.parse.urlencode(form.fields).encode())
    try:
        with opener.open(request, timeout=20) as response:
            status, url = response.status, response.url
            body = response.read()
    except urllib.error.HTTPError as error:
        status, url, body = error.code, error.url, error.read()
    return opener, jar, status, url, body


def websocket(jar=None):
    request = urllib.request.Request(BASE + "/")
    if jar:
        jar.add_cookie_header(request)
    cookie = request.get_header("Cookie")
    target = urllib.parse.urlsplit(BASE)
    port = target.port or (443 if target.scheme == "https" else 80)
    host = target.netloc
    raw = socket.create_connection((target.hostname, port), timeout=10)
    connection = ssl.create_default_context(cafile=CA_FILE).wrap_socket(raw, server_hostname=target.hostname) if target.scheme == "https" else raw
    with connection:
        connection.settimeout(10)
        stream = connection.makefile("rwb", buffering=0)
        headers = ["GET / HTTP/1.1", "Host: " + host, "Upgrade: websocket",
                   "Connection: Upgrade", "Origin: " + BASE,
                   "Sec-WebSocket-Version: 13", "Sec-WebSocket-Protocol: bolt",
                   "Sec-WebSocket-Key: " + base64.b64encode(os.urandom(16)).decode()]
        if cookie:
            headers.append("Cookie: " + cookie)
        stream.write(("\r\n".join(headers) + "\r\n\r\n").encode())
        status = int(stream.readline().split()[1])
        while stream.readline() not in (b"\r\n", b""):
            pass
        if status != 101:
            return status, None
        # Negotiate Bolt 5.8, 5.4 or 5.0 through the authenticated WebSocket.
        payload = bytes.fromhex("6060b01700000805000004050000000500000000")
        mask = os.urandom(4)
        stream.write(bytes([0x82, 0x80 | len(payload)]) + mask +
                     bytes(value ^ mask[i % 4] for i, value in enumerate(payload)))
        header = stream.read(2)
        assert len(header) == 2 and header[0] & 15 == 2, "Expected binary Bolt response"
        size = header[1] & 127
        if size == 126:
            size = struct.unpack("!H", stream.read(2))[0]
        assert not header[1] & 128, "Server frame must not be masked"
        version = stream.read(size)
        assert len(version) == 4 and version != b"\0" * 4, "Bolt negotiation failed"
        return status, version.hex()


def main():
    anonymous, _ = client()
    for path in ("/browser/", "/"):
        with anonymous.open(BASE + path, timeout=15) as response:
            assert response.url.startswith(ISSUER + "/"), path
    assert websocket()[0] in (302, 401, 403), "Anonymous WebSocket reached Bolt"
    request = urllib.request.Request(BASE + "/db/neo4j/tx/commit",
        data=b'{"statements": [{"statement": "RETURN 1"}]}',
        headers={"Content-Type": "application/json", "X-Forwarded-User": "admin"})
    try:
        with anonymous.open(request, timeout=15) as response:
            assert response.url.startswith(ISSUER + "/"), "Anonymous query reached Neo4j"
    except urllib.error.HTTPError as error:
        assert error.code in (401, 403), error.code
    print("PASS anonymous HTTP and Bolt WebSocket require SSO")

    opener, jar, status, url, body = login(USERNAME, PASSWORD)
    assert status == 200 and url.startswith(BASE + "/browser/"), (status, urllib.parse.urlsplit(url).path)
    assert b"Neo4j Browser" in body, "Browser content not served"
    with opener.open(BASE + "/", timeout=15) as response:
        discovery = json.load(response)
    assert discovery["neo4j_edition"] == "community", discovery
    target = urllib.parse.urlsplit(BASE)
    bolt = urllib.parse.urlsplit(discovery["bolt_direct"])
    expected_port = target.port or (443 if target.scheme == "https" else 80)
    assert (bolt.hostname, bolt.port) == (target.hostname, expected_port), discovery
    print("PASS Keycloak PKCE login, Browser assets and Community discovery")

    query = urllib.request.Request(BASE + "/db/neo4j/tx/commit",
        data=json.dumps({"statements": [{"statement": "RETURN 1 AS ok"}]}).encode(),
        headers={"Content-Type": "application/json"})
    with opener.open(query, timeout=15) as response:
        result = json.load(response)
    assert not result["errors"] and result["results"][0]["data"][0]["row"] == [1], result
    print("PASS authenticated database query")

    query = urllib.request.Request(BASE + "/db/neo4j/query/v2",
        data=b'{"statement": "RETURN 2 AS ok"}',
        headers={"Content-Type": "application/json"})
    with opener.open(query, timeout=15) as response:
        result = json.load(response)
    assert not result.get("errors") and result["data"]["values"] == [[2]], result
    print("PASS authenticated Query API request")

    status, version = websocket(jar)
    assert status == 101
    print("PASS authenticated Bolt negotiation over WebSocket:", version)

    denied = DENIED_USERNAME
    if denied:
        _, _, status, _, _ = login(denied, PASSWORD)
        assert status == 403, f"User without an allowed group received {status}"
        print("PASS user without an allowed group is denied")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=BASE)
    parser.add_argument("--issuer", default=ISSUER)
    parser.add_argument("--ca-file")
    parser.add_argument("--username", default=USERNAME)
    parser.add_argument("--denied-username", default=DENIED_USERNAME)
    args = parser.parse_args()
    BASE, ISSUER, CA_FILE = args.url.rstrip("/"), args.issuer.rstrip("/"), args.ca_file
    USERNAME, DENIED_USERNAME = args.username, args.denied_username
    PASSWORD = os.environ.get("TEST_PASSWORD") or demo_password()
    if not PASSWORD:
        parser.error("Set TEST_PASSWORD or start the demo first")
    main()
