import os
import sys

# Add the project root directory to sys.path
# This allows tests to import modules from the root directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
