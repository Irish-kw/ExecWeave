from __future__ import annotations

_TREE_CSS = r"""
.execweave-agent-tree{display:grid;gap:7px}.execweave-agent-tree-root{display:flex;align-items:center;gap:8px;padding:7px 9px;border:1px solid color-mix(in srgb,var(--selected,var(--accent)) 42%,var(--border));border-radius:8px;background:color-mix(in srgb,var(--panel2) 88%,var(--selected,var(--accent)) 7%)}.execweave-agent-tree-root::before{content:"";width:7px;height:7px;border-radius:50%;background:var(--selected,var(--accent));box-shadow:0 0 0 3px color-mix(in srgb,var(--selected,var(--accent)) 16%,transparent)}.execweave-agent-tree-root strong{font-size:11px}.execweave-agent-tree-root span{font-size:9px;color:var(--muted)}.execweave-agent-tree-body{display:grid;gap:7px;padding-left:10px;border-left:1px solid var(--border)}.execweave-agent-child{position:relative}.execweave-agent-child::before{content:"";position:absolute;left:-11px;top:18px;width:10px;border-top:1px solid var(--border)}.execweave-agent-path{font:9px/1.3 ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--muted);margin:2px 0 5px;overflow-wrap:anywhere}.execweave-root-conversation{border-color:color-mix(in srgb,var(--selected,var(--accent)) 28%,var(--border))}
""".strip()

_TREE_JS = r"""
<script>
(()=>{
  const configs=[
    {panel:'#execweave-conversation-panel',list:'.execweave-conversation-list',row:'.execweave-conversation-row',title:'.execweave-conversation-title',meta:'.execweave-conversation-message-meta'},
    {panel:'#conversation-records',list:'.conversation-live-list',row:'.conversation-live-row',title:'.conversation-live-title',meta:'.conversation-live-message-meta'}
  ];
  const parseTitle=text=>{const raw=String(text||''),parts=raw.split(' · ');return{path:parts[0]||'',suffix:parts.length>1?` · ${parts.slice(1).join(' · ')}`:''}};
  function treeify(config){
    const panel=document.querySelector(config.panel);if(!panel)return;
    const list=panel.querySelector(config.list);if(!list||list.dataset.execweaveAgentTree==='1')return;
    const rows=[...list.querySelectorAll(config.row)];if(!rows.length)return;
    const parsed=rows.map(row=>({row,title:row.querySelector(config.title),...parseTitle(row.querySelector(config.title)?.textContent)}));
    if(!parsed.some(item=>item.path==='/root'||item.path.startsWith('/root/')))return;
    list.dataset.execweaveAgentTree='1';list.classList.add('execweave-agent-tree');
    const root=document.createElement('div');root.className='execweave-agent-tree-root';
    const label=document.createElement('strong');label.textContent='/root';const hint=document.createElement('span');hint.textContent='agents started in this run';root.append(label,hint);
    const body=document.createElement('div');body.className='execweave-agent-tree-body';
    list.replaceChildren(root,body);
    parsed.sort((a,b)=>a.path.localeCompare(b.path));
    for(const item of parsed){
      const {row,title,path,suffix}=item;if(!title)continue;
      if(path==='/root'){
        title.hidden=true;row.classList.add('execweave-root-conversation');body.appendChild(row);
      }else{
        const leaf=path.split('/').filter(Boolean).pop()||path;title.textContent=`${leaf}${suffix}`;
        const pathLine=document.createElement('div');pathLine.className='execweave-agent-path';pathLine.textContent=path;
        title.insertAdjacentElement('afterend',pathLine);
        const depth=Math.max(1,path.split('/').filter(Boolean).length-1);row.classList.add('execweave-agent-child');row.style.marginLeft=`${Math.min(depth-1,4)*12}px`;body.appendChild(row);
      }
      for(const meta of row.querySelectorAll(config.meta)){
        const text=String(meta.textContent||'');
        if(path&&text.startsWith(`${path} · `))meta.textContent=text.slice(path.length+3);
      }
    }
  }
  function run(){for(const config of configs)treeify(config)}
  run();setTimeout(run,0);setTimeout(run,250);
  for(const config of configs){const panel=document.querySelector(config.panel);if(panel)new MutationObserver(()=>queueMicrotask(run)).observe(panel,{childList:true,subtree:true})}
})();
</script>
""".strip()


def _inject(html: str) -> str:
    if "execweave-agent-tree-root" not in html:
        html = html.replace("</style>", _TREE_CSS + "\n</style>", 1)
        html = html.replace("</body>", _TREE_JS + "\n</body>", 1)
    return html


def inject_live_conversation_tree(html: str) -> str:
    return _inject(html)


def inject_standalone_conversation_tree(html: str) -> str:
    return _inject(html)
