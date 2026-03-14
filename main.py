#!/usr/bin/env python3
"""
LLM Router - Main Entry Point
"""
import os
import sys

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from router import main

if __name__ == "__main__":
    main()
