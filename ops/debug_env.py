
import sys
import os

print(f"Python Executable: {sys.executable}")
print(f"Python Version: {sys.version}")
print(f"Current Working Directory: {os.getcwd()}")
print("Path:")
for p in sys.path:
    print(f"  {p}")

print("\nAttempting to import jinja2...")
try:
    import jinja2
    print(f"✅ jinja2 imported successfully. File: {jinja2.__file__}")
    print(f"Version: {jinja2.__version__}")
except ImportError as e:
    print(f"❌ Failed to import jinja2: {e}")

print("\nAttempting to verify pip installed packages...")
try:
    from importlib.metadata import distributions
    pkgs = [d.metadata['Name'] for d in distributions()]
    if 'Jinja2' in pkgs or 'jinja2' in pkgs:
        print("✅ Jinja2 found in importlib.metadata")
    else:
        print("❌ Jinja2 NOT found in importlib.metadata")
except Exception as e:
    print(f"Metadata check failed: {e}")
