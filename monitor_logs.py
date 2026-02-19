
import os
import shutil
import logging
from app import create_app

# Setup simple logger for this script
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger('monitor_logs')

def check_log_health():
    """
    Monitors log file size and disk usage.
    Alerts if disk usage > 90%.
    """
    app = create_app('production')
    
    with app.app_context():
        log_dir = os.path.join(app.root_path, '..', 'logs')
        log_file = os.path.join(log_dir, 'app.log')
        
        # 1. Check Log File Size
        if os.path.exists(log_file):
            size_bytes = os.path.getsize(log_file)
            size_mb = size_bytes / (1024 * 1024)
            logger.info(f"Log Size: {size_mb:.2f} MB")
            
            # Warn if single log file is unexpectedly huge (rotation should prevent this)
            if size_mb > 50: 
                logger.warning(f"⚠️ Log file is unusually large: {size_mb:.2f} MB. Rotation might be failing.")
        else:
            logger.warning("⚠️ Log file not found.")

        # 2. Check Disk Usage
        total, used, free = shutil.disk_usage(log_dir)
        percent_used = (used / total) * 100
        free_gb = free / (2**30)
        
        logger.info(f"Disk Usage: {percent_used:.1f}% ({free_gb:.1f} GB Free)")
        
        if percent_used > 90:
            alert_msg = f"CRITICAL: Disk usage is {percent_used:.1f}%. Logs might consume remaining space."
            logger.critical(alert_msg)
            # Send Email Alert (reusing the helper from main routes or separate logic)
            # For this script, we'll log to stderr which cron/task scheduler captures
            import sys
            print(alert_msg, file=sys.stderr)

if __name__ == "__main__":
    try:
        check_log_health()
        print("✅ Monitor check complete.")
    except Exception as e:
        logger.error(f"Monitor failed: {e}")
        exit(1)
