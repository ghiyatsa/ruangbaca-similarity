"""
Konfigurasi pytest — shared fixtures dan path setup.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
