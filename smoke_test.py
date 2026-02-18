import urllib.request
import urllib.error

print("=" * 50)
print("Mall Billing System — Phase 2 Smoke Tests")
print("=" * 50)

# ── Test 1: Dashboard must redirect to /auth/login ──────────────
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

opener = urllib.request.build_opener(NoRedirect)
try:
    opener.open('http://127.0.0.1:5000/')
    print("FAIL: Dashboard returned 200 — expected a redirect")
except urllib.error.HTTPError as e:
    loc = e.headers.get('Location', '?')
    print("Test 1 — Dashboard protection:")
    print("  Status : " + str(e.code))
    print("  Location: " + loc)
    if '/auth/login' in loc:
        print("  PASS: Correctly redirects unauthenticated users to login")
    else:
        print("  FAIL: Unexpected redirect target")

# ── Test 2: Login page returns 200 with correct form ────────────
print("\nTest 2 — Login page:")
r = urllib.request.urlopen('http://127.0.0.1:5000/auth/login')
html = r.read().decode()
print("  Status          : " + str(r.status))
print("  Has Sign in btn : " + str("Sign in" in html))
print("  Has username    : " + str('name="username"' in html))
print("  Has password    : " + str('name="password"' in html))
print("  Has POST method : " + str('method="POST"' in html))
if r.status == 200 and 'name="username"' in html:
    print("  PASS: Login page renders correctly")
else:
    print("  FAIL: Login page missing expected elements")

# ── Test 3: Logout redirects to login ───────────────────────────
print("\nTest 3 — Logout route:")
try:
    opener.open('http://127.0.0.1:5000/auth/logout')
except urllib.error.HTTPError as e:
    loc = e.headers.get('Location', '?')
    print("  Status  : " + str(e.code))
    print("  Location: " + loc)
    if '/auth/login' in loc:
        print("  PASS: Logout redirects to login")
    else:
        print("  FAIL: Unexpected redirect target")

print("\n" + "=" * 50)
print("Smoke tests complete.")
print("=" * 50)
