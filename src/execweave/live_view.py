from __future__ import annotations

from .live_view_markup import LIVE_MARKUP
from .live_view_script_a import LIVE_SCRIPT_A
from .live_view_script_b import LIVE_SCRIPT_B
from .live_view_script_c import LIVE_SCRIPT_C
from .live_view_style import LIVE_STYLE

LIVE_HTML = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ExecWeave Live</title>
<style>
{LIVE_STYLE}
</style>
</head>
<body>
{LIVE_MARKUP}
<script>
{LIVE_SCRIPT_A}{LIVE_SCRIPT_B}{LIVE_SCRIPT_C}
</script>
</body>
</html>"""
