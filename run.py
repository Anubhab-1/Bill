import eventlet
eventlet.monkey_patch()

import os
from dotenv import load_dotenv
from app import create_app, socketio

load_dotenv()

config_name = os.environ.get('FLASK_ENV', 'development')
app = create_app(config_name)

if __name__ == '__main__':
    socketio.run(
        app,
        host='0.0.0.0',
        port=int(os.environ.get('PORT', 5000)),
        debug=(config_name == 'development'),
        use_reloader=True
    )
