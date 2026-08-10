"""
WSGI entry point for production deployment
"""

import os

from app.core.factory import create_app

# Get environment
env = os.environ.get("FLASK_ENV", "development")
app = create_app(env)

if __name__ == "__main__":
    # Only for local development
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=app.debug)
