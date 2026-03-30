#!/usr/bin/env python3
"""Initialize v8 database"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Import from v8
from importlib import util
spec = util.spec_from_file_location("main_v8", os.path.join(os.path.dirname(__file__), 'src', 'main-v8-improved.py'))
main_v8 = util.module_from_spec(spec)
spec.loader.exec_module(main_v8)

# Initialize
print("Initializing database...")
main_v8.init_db()
print("Database initialized!")

print("Creating admin key...")
admin_key = main_v8.create_admin_key()
if admin_key:
    print(f"Admin API Key: {admin_key}")
    print("SAVE THIS KEY - it won't be shown again!")
else:
    print("Admin key already exists")

print("\nDatabase ready for testing!")
