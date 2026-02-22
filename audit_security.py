import os
from app import create_app

def audit_phase8():
    app = create_app('production')
    print("PHASE 8 — SECURITY HARDENING CHECK\n")
    
    with app.app_context():
        # 1. DEBUG Mode
        debug = app.config.get('DEBUG')
        print(f"1. DEBUG=False: {'PASS' if not debug else 'FAIL'}")
        
        # 2. Secret Key
        secret = app.config.get('SECRET_KEY')
        is_hardcoded = secret == 'dev-key-placeholder' or not secret
        print(f"2. SECRET_KEY configured (not default): {'PASS' if not is_hardcoded else 'FAIL'}")
        
        # 3. Session Security
        cookie_ht = app.config.get('SESSION_COOKIE_HTTPONLY', True)
        cookie_ss = app.config.get('SESSION_COOKIE_SAMESITE', 'Lax')
        print(f"3. Session Cookies Secure (HTTPOnly): {'PASS' if cookie_ht else 'FAIL'}")
        print(f"4. Session Cookies SameSite (Lax/Strict): {'PASS' if cookie_ss in ['Lax', 'Strict'] else 'FAIL'}")
        
        # 4. CSRF Protection
        has_csrf = 'csrf' in app.extensions
        print(f"5. CSRF Protection Active: {'PASS' if has_csrf else 'FAIL'}")

if __name__ == "__main__":
    audit_phase8()
