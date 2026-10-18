#!/usr/bin/env python3
import argparse
from collections import Counter
import json
import random
import threading
import time
import urllib.error
import urllib.request

status_counts = Counter()
counts_lock = threading.Lock()
known_ids = []
ids_lock = threading.Lock()


def record_status(code: str):
    with counts_lock:
        status_counts[code] += 1


def add_id(task_id: int):
    with ids_lock:
        known_ids.append(task_id)
        if len(known_ids) > 1000:
            known_ids.pop(0)


def get_random_id() -> int:
    with ids_lock:
        if known_ids:
            return random.choice(known_ids)
        return random.randint(1, 100)


def worker(
    base_url: str,
    stop_event: threading.Event,
    rps_per_worker: float,
    error_rate: float,
    slow_rate: float,
):
    interval = 1.0 / max(rps_per_worker, 0.1)
    req_counter = 0

    while not stop_event.is_set():
        start_time = time.time()
        req_counter += 1
        r = random.random()

        try:
            if r < error_rate:
                url = f"{base_url}/debug/error"
                req = urllib.request.Request(url, method="GET")
                with urllib.request.urlopen(req, timeout=5) as resp:
                    record_status(str(resp.status))
            elif r < (error_rate + slow_rate):
                url = f"{base_url}/debug/slow?ms=800"
                req = urllib.request.Request(url, method="GET")
                with urllib.request.urlopen(req, timeout=10) as resp:
                    record_status(str(resp.status))
            else:
                normal_r = random.random()
                if normal_r < 0.60:
                    url = f"{base_url}/tasks"
                    data = json.dumps({"title": f"Load task {req_counter}"}).encode(
                        "utf-8"
                    )
                    req = urllib.request.Request(
                        url,
                        data=data,
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        record_status(str(resp.status))
                        try:
                            body = json.loads(resp.read().decode("utf-8"))
                            if "id" in body:
                                add_id(body["id"])
                        except Exception:
                            pass
                elif normal_r < 0.90:
                    url = f"{base_url}/tasks"
                    req = urllib.request.Request(url, method="GET")
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        record_status(str(resp.status))
                else:
                    task_id = get_random_id()
                    method = "GET" if random.random() < 0.5 else "DELETE"
                    url = f"{base_url}/tasks/{task_id}"
                    req = urllib.request.Request(url, method=method)
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        record_status(str(resp.status))
        except urllib.error.HTTPError as e:
            record_status(str(e.code))
        except Exception:
            record_status("conn_err")

        elapsed = time.time() - start_time
        sleep_time = interval - elapsed
        if sleep_time > 0 and not stop_event.is_set():
            time.sleep(sleep_time)


def main():
    parser = argparse.ArgumentParser(description="Task API Load Generator")
    parser.add_argument(
        "--url",
        default="http://localhost:8081",
        help="Base URL (default: http://localhost:8081)",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=60,
        help="Duration in seconds (default: 60)",
    )
    parser.add_argument(
        "--rps",
        type=float,
        default=10,
        help="Requests per second (default: 10)",
    )
    parser.add_argument(
        "--error-rate",
        type=float,
        default=0.0,
        help="Fraction of requests sent to /debug/error",
    )
    parser.add_argument(
        "--slow-rate",
        type=float,
        default=0.0,
        help="Fraction of requests sent to /debug/slow?ms=800",
    )
    args = parser.parse_args()

    num_threads = min(4, max(1, int(args.rps / 2.5) or 1))
    rps_per_thread = args.rps / num_threads

    base_url = args.url.rstrip("/")
    print(
        f"Starting loadgen: url={base_url}, duration={args.duration}s, rps={args.rps}, "
        f"threads={num_threads}, error_rate={args.error_rate}, slow_rate={args.slow_rate}"
    )

    stop_event = threading.Event()
    threads = []
    for _ in range(num_threads):
        t = threading.Thread(
            target=worker,
            args=(
                base_url,
                stop_event,
                rps_per_thread,
                args.error_rate,
                args.slow_rate,
            ),
        )
        t.daemon = True
        t.start()
        threads.append(t)

    time.sleep(args.duration)
    stop_event.set()
    for t in threads:
        t.join(timeout=2.0)

    print("\nLoadgen completed. Status code counts:")
    for code, count in sorted(status_counts.items()):
        print(f"  {code}: {count}")


if __name__ == "__main__":
    main()
