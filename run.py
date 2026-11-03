"""Start Lanewise locally: python run.py [--port 5000] [--key-file path]

The Riot API key comes from the RIOT_API_KEY environment variable, a .env file, or --key-file.
"""
import argparse
import os
import re
from pathlib import Path

from lanewise.app import create_app


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 5000)))
    ap.add_argument("--key-file", type=Path, help="text file containing the key (kept out of the repo)")
    a = ap.parse_args()
    if a.key_file:
        m = re.search(r"RGAPI-[0-9a-fA-F-]+", a.key_file.read_text(encoding="utf-8"))
        if not m:
            raise SystemExit(f"no RGAPI key in {a.key_file}")
        os.environ["RIOT_API_KEY"] = m.group(0)
    create_app().run(host="127.0.0.1", port=a.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
