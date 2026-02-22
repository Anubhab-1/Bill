import os
import re

def inject_csrf():
    template_dir = r'c:\Users\anubhab samanta\OneDrive\Desktop\Mall\app\templates'
    
    # Regex for POST forms
    # Matches <form method="POST" ...> or <form ... method="POST" ...>
    form_post_re = re.compile(r'(<form[^>]+method=["\']POST["\'][^>]*>)', re.IGNORECASE)
    csrf_token_tag = '<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">'
    
    modified_count = 0
    
    for root, dirs, files in os.walk(template_dir):
        for file in files:
            if file.endswith('.html'):
                path = os.path.join(root, file)
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Skip if already has CSRF token
                if 'csrf_token' in content:
                    continue
                
                # Perform replacement
                new_content = form_post_re.sub(r'\1\n        ' + csrf_token_tag, content)
                
                if new_content != content:
                    with open(path, 'w', encoding='utf-8', newline='') as f:
                        f.write(new_content)
                    print(f"Injected CSRF into {os.path.relpath(path, template_dir)}")
                    modified_count += 1
    
    print(f"Total files modified: {modified_count}")

if __name__ == "__main__":
    inject_csrf()
