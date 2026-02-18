"""
app/utils/logging.py
───────────────────
Configures structured logging for production.
"""
import os
import logging
from logging.handlers import RotatingFileHandler
from flask import request


class RequestFormatter(logging.Formatter):
    """
    Custom formatter that injects request info (IP, user if logged in)
    into logs if context is available.
    """
    def format(self, record):
        if request:
            record.url = request.url
            record.remote_addr = request.remote_addr
        else:
            record.url = None
            record.remote_addr = None
        return super().format(record)


def setup_logging(app):
    """
    Configure rotating file logging: logs/app.log
    Max size: 5MB
    Backup count: 5 files
    Format: timestamp | level | module | message
    """
    log_dir = os.path.join(app.root_path, '..', 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    file_handler = RotatingFileHandler(
        os.path.join(log_dir, 'app.log'),
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=5
    )
    
    formatter = RequestFormatter(
        '%(asctime)s | %(levelname)s | %(name)s | %(remote_addr)s | %(url)s | %(message)s'
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)
    
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info("Mall Billing System startup")

