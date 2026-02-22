import os

def patch_init():
    path = r'c:\Users\anubhab samanta\OneDrive\Desktop\Mall\app\__init__.py'
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Targeted replacement for extensions
    old = "    # ── Extensions ────────────────────────────────────────────────\n    # ── Extensions ────────────────────────────────────────────────\n    db.init_app(app)"
    new = "    # ── Extensions ────────────────────────────────────────────────\n    from flask_wtf.csrf import CSRFProtect\n    csrf = CSRFProtect()\n    csrf.init_app(app)\n\n    db.init_app(app)"
    
    if old in content:
        content = content.replace(old, new)
        with open(path, 'w', encoding='utf-8', newline='') as f:
            f.write(content)
        print("Patched app/__init__.py")
    else:
        # Try without the duplicate line
        old2 = "    # ── Extensions ────────────────────────────────────────────────\n    db.init_app(app)"
        if old2 in content:
            content = content.replace(old2, new)
            with open(path, 'w', encoding='utf-8', newline='') as f:
                f.write(content)
            print("Patched app/__init__.py (no duplicate line found)")
        else:
            print("Could not find TargetContent in app/__init__.py")
            # Print content to debug
            # print(repr(content[500:1500]))

def patch_base():
    path = r'c:\Users\anubhab samanta\OneDrive\Desktop\Mall\app\templates\base.html'
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    old = '  <!-- HTMX -->\n  <script src="https://unpkg.com/htmx.org@1.9.10" defer></script>'
    new = '  <!-- HTMX -->\n  <script src="https://unpkg.com/htmx.org@1.9.10" defer></script>\n  <script>\n    document.addEventListener(\'htmx:configRequest\', (event) => {\n      event.detail.headers[\'X-CSRFToken\'] = \'{{ csrf_token() }}\';\n    });\n  </script>'
    
    if old in content:
        content = content.replace(old, new)
        with open(path, 'w', encoding='utf-8', newline='') as f:
            f.write(content)
        print("Patched base.html")
    else:
        print("Could not find TargetContent in base.html")

if __name__ == "__main__":
    patch_init()
    patch_base()
