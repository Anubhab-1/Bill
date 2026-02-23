def main():
    import re
    import requests

    sess = requests.Session()
    res = sess.get('http://127.0.0.1:8080/auth/login')
    m = re.search(r'name="csrf_token"[^>]+value="([^"]+)"', res.text)
    if not m:
        m = re.search(r'value="([^"]+)"[^>]+name="csrf_token"', res.text)
    print('TOKEN:', m.group(1) if m else 'NOT FOUND')
    if m:
        sess.headers.update({
            'X-CSRFToken': m.group(1),
            'Referer': 'http://127.0.0.1:8080/auth/login',
            'Origin': 'http://127.0.0.1:8080',
        })
        res2 = sess.post(
            'http://127.0.0.1:8080/auth/login',
            data={'username': 'admin', 'password': 'Admin@2026', 'csrf_token': m.group(1)},
        )
        print('LOGIN STATUS:', res2.status_code)

        # Try billing complete to make sure it works too
        res3 = sess.get('http://127.0.0.1:8080/billing/')
        print('BILLING STATUS:', res3.status_code)


if __name__ == '__main__':
    main()

