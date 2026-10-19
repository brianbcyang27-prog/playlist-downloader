"""Entry point so the app can be launched three ways:

    python -m app                 # package form
    python -m app.server          # module form
    PyInstaller bundle            # frozen executable

All of them funnel into `app.server.main`.
"""

from __future__ import annotations

from app.server import main

if __name__ == "__main__":
    raise SystemExit(main())
