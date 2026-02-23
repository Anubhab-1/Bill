def main():
    import re
    import requests

    sess = requests.Session()
    res = sess.get('https://mall-billing-system-geli.onrender.com/auth/login')

    m = re.search(r'name="csrf_token"[^>]+value="([^"]+)"', res.text)
    if not m:
        m = re.search(r'value="([^"]+)"[^>]+name="csrf_token"', res.text)

    print('Matches:', bool(m))
    if m:
        print('Token:', m.group(1))

        # Test setting header
        sess.headers.update({'X-CSRFToken': m.group(1)})
        res2 = sess.post(
            'https://mall-billing-system-geli.onrender.com/auth/login',
            data={'username': 'admin', 'password': 'Admin@2026'},
        )
        print('Login Status with Header:', res2.status_code)

        # Test setting data instead of header
        sess2 = requests.Session()
        # Need a fresh token for the new session because CSRF is tied to the session cookie.
        res3 = sess2.get('https://mall-billing-system-geli.onrender.com/auth/login')
        m3 = re.search(r'name="csrf_token"[^>]+value="([^"]+)"', res3.text)
        if not m3:
            m3 = re.search(r'value="([^"]+)"[^>]+name="csrf_token"', res3.text)

        res4 = sess2.post(
            'https://mall-billing-system-geli.onrender.com/auth/login',
            data={'username': 'admin', 'password': 'Admin@2026', 'csrf_token': m3.group(1)},
        )
        print('Login Status with Data:', res4.status_code)


if __name__ == '__main__':
    main()
