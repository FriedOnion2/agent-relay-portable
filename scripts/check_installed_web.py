"""Run with the Python of a freshly installed wheel: the web assets referenced by index.html must be present."""
import os
import re
import sys

import relay_web
from relay.messages import text

root = list(relay_web.__path__)[0]
with open(os.path.join(root, "index.html"), encoding="utf-8") as handle:
    page = handle.read()
files = set(re.findall(r'(?:src|href)="/static/([^"]+)"', page)) | {"index.html", "locales.zh.json", "locales.en.json"}
missing = sorted(name for name in files if not os.path.isfile(os.path.join(root, name)))
if len(files) < 10 or missing:
    sys.exit("web assets missing from the installed package: %s (looked in %s)" % (missing or "too few referenced", root))
if text("msg.session_unreadable") != "会话无法读取":
    sys.exit("message catalog not packaged correctly")
print("installed web assets ok:", len(files), "files")
