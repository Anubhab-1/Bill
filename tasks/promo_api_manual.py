import urllib.request, urllib.parse, re

req_get = urllib.request.Request('http://127.0.0.1:5000/auth/login')
with urllib.request.urlopen(req_get) as r:
    html = r.read().decode('utf-8')
    csrf_token = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
    cookie_str = r.headers.get('Set-Cookie', '')
    cookie = [c for c in cookie_str.split(';') if 'session=' in c]
    cookie = cookie[0] if cookie else ''

data = urllib.parse.urlencode({'csrf_token': csrf_token, 'pin': '1234'}).encode()
req_login = urllib.request.Request('http://127.0.0.1:5000/auth/login', data=data, headers={'Cookie': cookie})
try:
    with urllib.request.urlopen(req_login) as r:
        cookie_str = r.headers.get('Set-Cookie', '')
        cookie_list = [c for c in cookie_str.split(';') if 'session=' in c]
        if cookie_list: cookie = cookie_list[0]
except urllib.error.HTTPError as e:
    import sys
    print("Login error", e.code)
    sys.exit(1)

req_get2 = urllib.request.Request('http://127.0.0.1:5000/promotions/new', headers={'Cookie': cookie})
with urllib.request.urlopen(req_get2) as r:
    html = r.read().decode('utf-8')
    csrf_token = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)

form_data = {
    'csrf_token': csrf_token,
    'name': 'Test Promo 123',
    'promo_type': 'bill_percentage',
    'param_percent': '10',
    'is_active': '1'
}
data2 = urllib.parse.urlencode(form_data).encode()
req_post = urllib.request.Request('http://127.0.0.1:5000/promotions/new', data=data2, headers={'Cookie': cookie})
try:
    with urllib.request.urlopen(req_post) as r:
        with open('test_res.html', 'w') as f:
            f.write(r.read().decode('utf-8'))
        print('Saved to test_res.html, HTTP:', r.getcode())
except urllib.error.HTTPError as e:
    print('Failed with HTTP', e.code)
