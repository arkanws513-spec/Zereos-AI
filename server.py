"""Railway entry point for the Jenny/Zereos gateway."""
from __future__ import annotations

import os

from jenny.android_entry import run_gateway


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    run_gateway("/tmp/jenny", host="0.0.0.0", port=port)
