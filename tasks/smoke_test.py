from run import app


def run_smoke_tests():
    paths = ['/', '/auth/login']

    with app.test_client() as client:
        for path in paths:
            response = client.get(path, follow_redirects=False)
            assert response.status_code in (200, 302), (
                f'{path} returned {response.status_code}, expected 200 or 302'
            )
            print(f'{path}: {response.status_code}')


if __name__ == '__main__':
    run_smoke_tests()
    print('Smoke tests complete.')
