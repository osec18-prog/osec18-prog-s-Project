"""
Analyze app.py for duplicate Flask routes and report them.
"""
import re

with open('app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Track all route decorators
routes = {}  # url -> list of (line_number, function_name, methods)

for i, line in enumerate(lines, 1):
    m = re.match(r'@app\.route\(["\']([^"\']+)["\']', line.strip())
    if m:
        url = m.group(1)
        methods_match = re.search(r'methods=\[([^\]]*)\]', line)
        methods = methods_match.group(1) if methods_match else 'GET'
        
        # Get the function name on the next line
        func_name = '???'
        if i < len(lines):
            fn_match = re.match(r'def (\w+)\(', lines[i])
            if fn_match:
                func_name = fn_match.group(1)
        
        if url not in routes:
            routes[url] = []
        routes[url].append((i, func_name, methods))

# Also check for duplicate @app.route decorators specifically in the same block
# (the corrupt file has duplicate blocks of code)
for url, entries in sorted(routes.items()):
    if len(entries) > 1:
        print(f"DUPLICATE ROUTE: {url}")
        for entry in entries:
            print(f"  Line {entry[0]}: function={entry[1]}(), methods=[{entry[2]}]")
        print()

# Count total unique routes
print(f"\nTotal unique route URLs: {len(routes)}")
print(f"Total with duplicates: {sum(1 for v in routes.values() if len(v) > 1)}")

