#!/usr/bin/env python3
# OD_CopyPasteExternal — exchange-file watcher (Python 3, stdlib only)
#
# Watches the ODVertexData exchange file and re-converts it to a stable OBJ
# path (OD_CPE.obj next to it) every time it changes. This gives one-way
# live consumption for applications that read OBJ but have no scripting API
# — e.g. Light Tracer Render: import OD_CPE.obj once, then re-import/refresh
# after each copy from any other application.
#
# Usage:
#   od_watch.py [--interval SECONDS] [--out FILE]
# Stop with Ctrl-C.

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import od_obj  # noqa: E402  (also loads odformat)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Re-convert the ODVertexData exchange file to OBJ whenever it changes."
    )
    parser.add_argument("--interval", type=float, default=1.0, help="poll interval in seconds (default 1)")
    parser.add_argument("--out", metavar="FILE", help="OBJ path to keep updated (default: OD_CPE.obj next to the exchange file)")
    args = parser.parse_args(argv)

    src = od_obj.odformat.data_file_path()
    out = args.out or os.path.join(os.path.dirname(src), "OD_CPE.obj")
    print("watching %s -> %s (Ctrl-C to stop)" % (src, out))

    last = None
    while True:
        try:
            stamp = os.stat(src).st_mtime_ns
        except OSError:
            stamp = None
        if stamp is not None and stamp != last:
            last = stamp
            try:
                od_obj.main(["--to-obj", "--in", src, "--out", out])
            except (OSError, ValueError) as exc:
                print("conversion failed (will retry on next change): %s" % exc)
        try:
            time.sleep(args.interval)
        except KeyboardInterrupt:
            print("stopped.")
            return 0


if __name__ == "__main__":
    sys.exit(main())
