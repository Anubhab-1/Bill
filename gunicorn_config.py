import multiprocessing

# Gunicorn Production Configuration
# Workers: (2x CPU Count) + 1 is the official recommendation for typical IO-bound apps
workers = multiprocessing.cpu_count() * 2 + 1
threads = 2
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
