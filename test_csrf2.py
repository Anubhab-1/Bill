import requests
import re

sess = requests.Session()
res = sess.get('https://mall-billing-system-geli.onrender.com/auth/login')

m = re.search(r'name="csrf_token"[^>]+value="([^"]+)"', res.text)
if not m:
    m = re.search(r'value="([^"]+)"[^>]+name="csrf_token"', res.text)

if m:
    token = m.group(1)
    
    sess.headers.update({
        'X-CSRFToken': token,
        'Referer': 'https://mall-billing-system-geli.onrender.com/auth/login',
        'Origin': 'https://mall-billing-system-geli.onrender.com'
    })
    
    res2 = sess.post('https://mall-billing-system-geli.onrender.com/auth/login', data={'username': 'admin', 'password': 'Admin@2026', 'csrf_token': token})
    print('Login Status:', res2.status_code)
