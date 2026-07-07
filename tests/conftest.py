"""
Konfigurasi pytest — shared fixtures dan path setup.
"""
import sys
import os

# Pastikan root project ada di sys.path agar import app.* berjalan
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
