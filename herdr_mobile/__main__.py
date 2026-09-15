import argparse
import os

from .server import serve


def main() -> None:
    ap = argparse.ArgumentParser(prog="herdr-mobile", description="Mobile web UI for Herdr")
    ap.add_argument("--host", default=os.environ.get("HERDR_MOBILE_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("HERDR_MOBILE_PORT", "9080")))
    a = ap.parse_args()
    serve(a.host, a.port)


if __name__ == "__main__":
    main()
