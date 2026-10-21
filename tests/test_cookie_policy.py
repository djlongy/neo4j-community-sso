"""The local demo exception must never send Secure cookies over remote HTTP."""
import http.cookiejar
import urllib.request
from check_sso import LocalDemoCookiePolicy

cookie = http.cookiejar.Cookie(0, "session", "test", None, False, "localhost", False,
    False, "/", True, True, None, True, None, None, {}, False)
policy = LocalDemoCookiePolicy()
assert policy.return_ok_secure(cookie, urllib.request.Request("http://localhost:9480/"))
assert policy.return_ok_secure(cookie, urllib.request.Request("https://idp.example.test/"))
assert not policy.return_ok_secure(cookie, urllib.request.Request("http://idp.example.test/"))
print("PASS Secure cookies remain HTTPS-only outside localhost")
