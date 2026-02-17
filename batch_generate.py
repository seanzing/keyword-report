"""Batch generate keyword reports and append shareable URLs to CSV."""

import csv
import http.client
import json
import ssl
import time
import urllib.parse
from urllib.parse import urlparse

BASE_URL = "https://keyword-report-production.up.railway.app"
CSV_PATH = "Contacts_With_Websites.csv"
OUTPUT_PATH = "Contacts_With_Websites.csv"

def clean_url(url):
    """Strip path/query to get homepage URL."""
    parsed = urlparse(url.strip())
    return "{0}://{1}".format(parsed.scheme, parsed.netloc)


def generate_report(url):
    """
    Call the SSE endpoint using http.client for true streaming.
    Returns {"filename": ..., "business_name": ..., ...} on success, None on failure.
    """
    encoded_url = urllib.parse.quote(url, safe=":/")
    path = "/api/generate?url=" + urllib.parse.quote(encoded_url, safe="")

    parsed = urlparse(BASE_URL)
    ctx = ssl.create_default_context()
    conn = http.client.HTTPSConnection(parsed.netloc, timeout=180, context=ctx)

    try:
        conn.request("GET", path)
        resp = conn.getresponse()

        if resp.status != 200:
            print("    HTTP {0}".format(resp.status))
            return None

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
                if event_type == "progress" and data:
                    print("    " + data, flush=True)
                elif event_type == "complete" and data:
                    return json.loads(data)
                elif event_type == "error":
                    print("    ERROR: " + str(data), flush=True)
                    return None
                event_type = None
                data = None
    except Exception as e:
        print("    CONNECTION ERROR: " + str(e), flush=True)
        return None
    finally:
        conn.close()

    return None


def main():
    # Read CSV
    with open(CSV_PATH, newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = list(reader.fieldnames)

    # Add Report URL column if not present
    if "Report URL" not in fieldnames:
        fieldnames.append("Report URL")

    total = len(rows)
    success = 0
    failed = 0

    for i, row in enumerate(rows):
        deal = row["Deal Name"].strip()
        raw_url = row["Current Website"].strip()

        clean = clean_url(raw_url)
        print("\n[{0}/{1}] {2} -> {3}".format(i + 1, total, deal, clean), flush=True)

        result = generate_report(clean)

        if result and "filename" in result:
            share_url = BASE_URL + "/reports/" + result["filename"]
            row["Report URL"] = share_url
            success += 1
            print("    DONE -> " + share_url, flush=True)
        else:
            row["Report URL"] = ""
            failed += 1
            print("    FAILED", flush=True)

        # Write CSV after each generation (in case of crash)
        with open(OUTPUT_PATH, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        # Small delay between requests
        time.sleep(2)

    print("\n" + "=" * 60, flush=True)
    print("Done! Success: {0}, Failed: {1}".format(success, failed), flush=True)
    print("Updated CSV: " + OUTPUT_PATH, flush=True)


if __name__ == "__main__":
    main()
