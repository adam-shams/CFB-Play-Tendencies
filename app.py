"""
Root entry point for Streamlit Cloud deployment.
Adds the cfb_tendency_analyzer directory to sys.path and runs main.
"""
import sys
import os

# Add the app directory so all internal imports resolve correctly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "cfb_tendency_analyzer"))

from main import main

main()
