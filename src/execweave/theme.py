from __future__ import annotations

from pathlib import Path

_THEME_CSS = """
:root[data-theme="light"]{color-scheme:light;--bg:#f7f9fc;--panel:#ffffff;--panel2:#eef3f8;--text:#172033;--muted:#617083;--border:#cbd5e1;--edge:#64748b;--causal:#15803d;--noncausal:#b45309;--inferred:#7e22ce;--identity:#0369a1;--selected:#2563eb;--accent:#2563eb}
#execweave-theme-toggle{position:fixed;right:14px;bottom:14px;z-index:9999;border:1px solid var(--border);background:var(--panel);color:var(--text);border-radius:8px;padding:7px 10px;cursor:pointer;box-shadow:0 4px 18px rgba(15,23,42,.12)}
#execweave-theme-toggle:hover{border-color:var(--selected,var(--accent))}
#save-preset{position:fixed;right:14px;top:58px;z-index:9998;box-shadow:0 4px 18px rgba(15,23,42,.12)}
:root[data-theme="light"] .node text{fill:#f8fafc}:root[data-theme="light"] .node .node-type{fill:#cbd5e1}
""".strip()

_THEME_CONTROLS = r"""
<button id="execweave-theme-toggle" type="button" aria-label="Switch to light theme" title="Switch to light theme">Light</button>
<script>
(()=>{const key='execweave-theme',button=document.getElementById('execweave-theme-toggle');function apply(theme,persist=false){const next=theme==='light'?'light':'dark';document.documentElement.dataset.theme=next;const light=next==='light';button.textContent=light?'Dark':'Light';button.setAttribute('aria-label',light?'Switch to dark theme':'Switch to light theme');button.title=light?'Switch to dark theme':'Switch to light theme';if(persist){try{localStorage.setItem(key,next)}catch(_){}}}let initial='dark';try{if(localStorage.getItem(key)==='light')initial='light'}catch(_){}apply(initial);button.onclick=()=>apply(document.documentElement.dataset.theme==='light'?'dark':'light',true)})();
</script>
""".strip()


def inject_viewer_theme(html: str) -> str:
    """Inject the legacy standalone theme only when the page has no theme owner.

    The v0.7.9 unified dashboard already ships the visible ``#theme-toggle`` and
    its theme logic. Detect that real control instead of relying on a fake comment
    sentinel, so ``execweave view`` cannot add a second theme implementation.
    """
    if 'id="theme-toggle"' in html or 'id="execweave-theme-toggle"' in html:
        return html
    themed = html.replace("</style>", _THEME_CSS + "\n</style>", 1)
    return themed.replace("</body>", _THEME_CONTROLS + "\n</body>", 1)


def ensure_viewer_theme(path: str | Path) -> Path:
    output = Path(path).expanduser().resolve()
    html = output.read_text(encoding="utf-8")
    themed = inject_viewer_theme(html)
    if themed != html:
        output.write_text(themed, encoding="utf-8")
    return output
