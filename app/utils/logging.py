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
    # 1. File Logger (Try/Except for permissions)
    try:
        log_dir = os.path.join(app.root_path, '..', 'logs')
        os.makedirs(log_dir, exist_ok=True)
        
        file_handler = RotatingFileHandler(
            os.path.join(log_dir, 'app.log'),
            maxBytes=5 * 1024 * 1024,
            backupCount=5
        )
        file_handler.setFormatter(RequestFormatter(
            '%(asctime)s | %(levelname)s | %(name)s | %(remote_addr)s | %(url)s | %(message)s'
        ))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
    except Exception:
        pass # Fallback to stdout if filesystem is read-only

    # 2. Stdout Logger (Critical for Render/Cloud logs)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(logging.Formatter(
        '%(asctime)s | %(levelname)s | %(message)s'
    ))
    stream_handler.setLevel(logging.INFO)
    app.logger.addHandler(stream_handler)

    app.logger.setLevel(logging.INFO)
    app.logger.info("Mall Billing System startup")

