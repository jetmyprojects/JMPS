"""Vercel serverless entrypoint for the Django app.

Vercel's Python runtime looks for a WSGI/ASGI callable named `app` (or
`application`) in files under `api/`. We expose the project's existing WSGI
application here and route all traffic to it via vercel.json rewrites.
"""
import os
import sys

# Ensure the project root (parent of this api/ dir) is importable so
# `config.wsgi` resolves when Vercel runs this file as the function entry.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.wsgi import application

app = application

# Deployed via Vercel (WSGI entrypoint). Push to main to trigger a redeploy.
