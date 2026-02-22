import os
from flask import current_app
from app import create_app

def audit_phase1():
    modes = ['development', 'testing', 'production']
    print("PHASE 1 — ENVIRONMENT VALIDATION\n")
    
    for mode in modes:
        print(f"--- Mode: {mode} ---")
        try:
            app = create_app(mode)
            with app.app_context():
                db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', 'NOT SET')
                print(f"  Active DB: {db_uri}")
                
                engine_options = app.config.get('SQLALCHEMY_ENGINE_OPTIONS', {})
                print(f"  Engine Options: {engine_options}")
                
                dialect = db_uri.split(':', 1)[0].lower() if db_uri and ':' in db_uri else ''
                pool_keys = {'pool_size', 'max_overflow', 'pool_timeout'}
                has_pool = any(k in engine_options for k in pool_keys)
                
                if dialect.startswith('postgresql'):
                    print(f"  Production/Postgres Logic: {'YES' if has_pool else 'NO'} (Pool expected)")
                else:
                    print(f"  Non-Postgres Logic: {'YES' if not has_pool else 'NO'} (No pool expected)")
                
                # Check for pool sizing specifically
                if has_pool:
                     print(f"    pool_size: {engine_options.get('pool_size')}")
                     print(f"    max_overflow: {engine_options.get('max_overflow')}")
        except Exception as e:
            print(f"  [ERROR] Failed to load {mode}: {e}")
        print("\n")

if __name__ == "__main__":
    audit_phase1()
