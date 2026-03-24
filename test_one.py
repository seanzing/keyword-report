"""Test a single URL through the Railway API and show full SSE output."""

import http.client
import ssl
import sys
import urllib.parse
from urllib.parse import urlparse

BASE_URL = "https://keyword-report-production.up.railway.app"


def clean_url(url):
    parsed = urlparse(url.strip())
    return "{0}://{1}".format(parsed.scheme, parsed.netloc)


def test_url(url):
    encoded_url = urllib.parse.quote(url, safe=":/")
    path = "/api/generate?url=" + urllib.parse.quote(encoded_url, safe="")

    parsed = urlparse(BASE_URL)
    ctx = ssl.create_default_context()
    conn = http.client.HTTPSConnection(parsed.netloc, timeout=180, context=ctx)

    try:
        conn.request("GET", path)
        resp = conn.getresponse()

        if resp.status != 200:
            print("HTTP {0}".format(resp.status))
            return

        event_type = None
        data = None
        while True:
            raw_line = resp.readline()
            if not raw_line:
                break
            line = raw_line.decode("utf-8", errors="replace").rstrip("\n\r")

            if line.startswith("event: "):
                event_type = line[7:]
            elif line.startswith("data: "):
                data = line[6:]
            elif line == "":
                if event_type and data:
                    print("[{0}] {1}".format(event_type, data), flush=True)
                event_type = None
                data = None
    finally:
        conn.close()


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "https://www.brodallpainting.com/"
    clean = clean_url(url)
    print("Testing: {0}".format(clean))
    test_url(clean)
