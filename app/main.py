"""Entry point.

  python3 -m app.main                 local, http://127.0.0.1:8765
  python3 -m app.main --reset         local, fresh demo data
  python3 -m app.main --hosted        public demo behind a TLS proxy (Render):
                                      binds 0.0.0.0:$PORT, reseeds on every start
"""

from __future__ import annotations

import argparse
import os
import sys
import webbrowser

from . import api, config, llm
from .db import DEFAULT_PASSPHRASE, Store
from .seed import USERS, seed
from .server import serve

DEFAULT_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "psychreport.db")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="PsychReport - local psychiatric report studio")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--reset", action="store_true", help="delete the database and reseed")
    parser.add_argument("--no-seed", action="store_true", help="start with an empty database")
    parser.add_argument("--open", action="store_true", help="open a browser window")
    parser.add_argument("--hosted", action="store_true",
                        help="public demo behind a TLS-terminating proxy (e.g. Render)")
    args = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass

    hosted = args.hosted or os.environ.get("PSYCHREPORT_HOSTED") == "1"
    if hosted:
        passphrase = os.environ.get("PSYCHREPORT_PASSPHRASE", "")
        if not passphrase or passphrase == DEFAULT_PASSPHRASE:
            print("REFUSING TO START: hosted mode requires PSYCHREPORT_PASSPHRASE to be set to a\n"
                  "generated secret. On Render, render.yaml generates one; for a manually created\n"
                  "service, add it under Environment.", file=sys.stderr)
            return 2
        config.enable_hosted()
        args.host = "0.0.0.0"
        args.port = int(os.environ.get("PORT", "10000"))
        # Every start is a clean demo: nothing a visitor typed survives a restart.
        args.reset = True
        args.no_seed = False
        args.open = False
    elif args.host not in ("127.0.0.1", "localhost"):
        print("REFUSING TO START: this application holds protected health information and binds to\n"
              "loopback only. Use --hosted only for a public demonstration with fictional data\n"
              "behind a TLS-terminating proxy.", file=sys.stderr)
        return 2

    if args.reset:
        for suffix in ("", "-wal", "-shm"):
            path = args.db + suffix
            if os.path.exists(path):
                os.remove(path)

    os.makedirs(os.path.dirname(args.db), exist_ok=True)
    store = Store(args.db)
    if not args.no_seed:
        seed(store)

    httpd = serve(api.router, lambda: api.Context(store), args.host, args.port)
    url = f"http://{args.host}:{args.port}/"

    print("=" * 74)
    print("  PsychReport - psychiatric evaluation to recipient-specific reports")
    print("=" * 74)
    print(f"  Serving   {url}" + ("   [HOSTED PUBLIC DEMO - reseeded on start]" if hosted else ""))
    print(f"  Database  {args.db}")
    status = llm.CONFIG.status()
    print("  AI model  " + ("not configured - fully offline (deterministic drafting + assistant)"
                            if not status["enabled"] else
                            f"{status['provider']}:{status['model']} at {status['endpoint']}"
                            + ("  [LOCAL]" if status["local"] else "  [REMOTE - de-identified]")))
    if status.get("blocked_reason"):
        print("            " + status["blocked_reason"])
    if store.using_default_passphrase:
        print("  WARNING   Using the built-in demonstration passphrase. Set PSYCHREPORT_PASSPHRASE")
        print("            before entering any real patient information.")
    print("  DEMO DATA Four fictional patients. No real PHI is included.")
    print("-" * 74)
    print("  Sign in with:")
    for username, password, name, role, _c, _n in USERS:
        print(f"    {username:<12} {password:<12} {name} ({role})")
    print("=" * 74)
    print("  Ctrl-C to stop.")

    if args.open:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
