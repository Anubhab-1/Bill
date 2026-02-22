import inspect
from app import create_app
from flask import current_app

def audit_phase2():
    app = create_app('development')
    print("PHASE 2 — ROUTE INTEGRITY SCAN\n")
    
    with app.app_context():
        routes = []
        for rule in app.url_map.iter_rules():
            # Filter out static
            if rule.endpoint == 'static':
                continue
                
            methods = ','.join(sorted(list(rule.methods - {'OPTIONS', 'HEAD'})))
            view_func = app.view_functions[rule.endpoint]
            
            # Extract decorators via inspection (simplified)
            # This is hard because decorators often hide original func
            # We will use grep for more reliable detection of @login_required etc.
            
            routes.append({
                'endpoint': rule.endpoint,
                'methods': methods,
                'rule': str(rule),
                'func_name': view_func.__name__
            })

        print(f"Total Routes found: {len(routes)}\n")
        print(f"{'Endpoint':<30} | {'Methods':<15} | {'Path'}")
        print("-" * 80)
        for r in sorted(routes, key=lambda x: x['rule']):
            print(f"{r['endpoint']:<30} | {r['methods']:<15} | {r['rule']}")

if __name__ == "__main__":
    audit_phase2()
