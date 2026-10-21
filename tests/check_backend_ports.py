"""Run from another pod to check the SSO entry point and backend isolation."""
import argparse
import socket

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--host", required=True, help="Application pod IP, not the Service IP")
args = parser.parse_args()

with socket.create_connection((args.host, 4180), timeout=5):
    pass
for port in (7474, 7687, 8080):
    try:
        connection = socket.create_connection((args.host, port), timeout=3)
    except OSError:
        continue
    connection.close()
    raise AssertionError(f"Private backend port {port} is reachable")
print("PASS SSO entry is reachable and all three backend ports are isolated")
