from __future__ import annotations

_LIVE_LAYOUT_CSS = r"""
#app{grid-template-rows:64px minmax(0,1fr) var(--activity-height,230px)!important}
#activity-panel{position:relative}
#activity-resizer{position:absolute;left:0;right:0;top:-5px;height:10px;z-index:20;cursor:ns-resize;touch-action:none}
#activity-resizer::before{content:"";position:absolute;left:50%;top:3px;width:54px;height:3px;transform:translateX(-50%);border-radius:999px;background:var(--border-strong);opacity:.72;transition:opacity .15s ease,background .15s ease}
#activity-resizer:hover::before,#activity-resizer.dragging::before{opacity:1;background:var(--selected)}
body.execweave-resizing-log{cursor:ns-resize!important;user-select:none!important}
@media(max-width:760px){#app{grid-template-rows:auto 520px auto 260px!important}#activity-resizer{display:none}}
""".strip()

_LIVE_LAYOUT_JS = r"""
<script>
(()=>{
  const app=document.getElementById('app'),panel=document.getElementById('activity-panel'),handle=document.getElementById('activity-resizer');
  if(!app||!panel||!handle)return;
  const storageKey='execweave.live.activity-height';
  const clamp=value=>Math.max(96,Math.min(Math.max(120,window.innerHeight-170),Math.round(value)));
  const apply=value=>{const height=clamp(value);app.style.setProperty('--activity-height',`${height}px`);return height};
  try{const saved=Number(localStorage.getItem(storageKey));if(Number.isFinite(saved)&&saved>0)apply(saved)}catch(_){}
  let startY=0,startHeight=0,dragging=false;
  handle.addEventListener('pointerdown',event=>{
    if(event.button!==0)return;
    dragging=true;startY=event.clientY;startHeight=panel.getBoundingClientRect().height;
    handle.classList.add('dragging');document.body.classList.add('execweave-resizing-log');
    try{handle.setPointerCapture(event.pointerId)}catch(_){}
    event.preventDefault();
  });
  handle.addEventListener('pointermove',event=>{
    if(!dragging)return;
    apply(startHeight+(startY-event.clientY));
  });
  const stop=event=>{
    if(!dragging)return;
    dragging=false;handle.classList.remove('dragging');document.body.classList.remove('execweave-resizing-log');
    try{handle.releasePointerCapture(event.pointerId)}catch(_){}
    try{localStorage.setItem(storageKey,String(Math.round(panel.getBoundingClientRect().height)))}catch(_){}
  };
  handle.addEventListener('pointerup',stop);handle.addEventListener('pointercancel',stop);
  handle.addEventListener('dblclick',()=>{const height=apply(230);try{localStorage.setItem(storageKey,String(height))}catch(_){}});
  window.addEventListener('resize',()=>{const current=panel.getBoundingClientRect().height;if(current)apply(current)});
})();
</script>
""".strip()


def inject_live_dashboard_layout(html: str) -> str:
    """Add a persistent drag handle for resizing the live log region."""
    if "id=\"activity-resizer\"" not in html:
        html = html.replace(
            '<section id="activity-panel">',
            '<section id="activity-panel"><div id="activity-resizer" role="separator" '
            'aria-label="Resize live logs" aria-orientation="horizontal" '
            'title="Drag to resize Live Logs · double-click to reset"></div>',
            1,
        )
    if "execweave.live.activity-height" not in html:
        html = html.replace("</style>", _LIVE_LAYOUT_CSS + "\n</style>", 1)
        html = html.replace("</body>", _LIVE_LAYOUT_JS + "\n</body>", 1)
    return html
