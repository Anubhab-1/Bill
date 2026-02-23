# Gunicorn Production Configuration
# Flask-SocketIO long-polling requires a single worker unless sticky sessions are guaranteed.
workers = 1
threads = 50
worker_class = 'gthread'

# Resilience
timeout = 120
max_requests = 1000
max_requests_jitter = 100
keepalive = 5

# Logging
accesslog = '-'       # Stdout
errorlog = '-'        # Stderr
loglevel = 'info'
capture_output = True
