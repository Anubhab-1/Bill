import os
from app import create_app

def main():
    os.environ["SECRET_KEY"] = "temp-verify-key"
    os.environ["DATABASE_URL"] = "postgresql://postgres:Galaxy%402006@localhost:5432/mall"

    app = create_app('development')
    with app.test_client() as client:
        # login as admin
        with client.session_transaction() as sess:
            sess['user_id'] = 1  # Assuming admin has ID 1
            sess['role'] = 'admin'

        response = client.get('/promotions/new')
        print(f"Status: {response.status_code}")
        if response.status_code == 500:
            print("Response received 500. Check logs or traceback below if it was caught.")
        else:
            print("Response received OK.")


if __name__ == '__main__':
    main()
