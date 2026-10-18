import sys
import urllib.request


def check() -> int:
    try:
        req = urllib.request.Request("http://127.0.0.1:8000/healthz")
        with urllib.request.urlopen(req, timeout=2) as response:
            if response.status == 200:
                return 0
            return 1
    except Exception:
        return 1


if __name__ == "__main__":
    sys.exit(check())
