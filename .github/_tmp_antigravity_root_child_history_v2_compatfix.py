from pathlib import Path

path = Path("src/execweave/viewer_agent_panel.py")
text = path.read_text(encoding="utf-8")
old = '''function canonicalRootRecord(){
  const roots=entries.filter(entryHasRootAuthority);
  const sourceIds=[...new Set(roots.map(entry=>String(entry?.source_id||'')).filter(Boolean))];
  if(sourceIds.length===1)return aggregate(roots.filter(entry=>String(entry?.source_id||'')===sourceIds[0]));
  if(sourceIds.length)return null;
  const agy=entries.filter(entry=>{
    const preview=entry?.conversation_preview;
    return String(entry?.provider||'').toLowerCase()==='antigravity'&&!!preview&&
      String(entry?.source_id||'').startsWith('agent:antigravity:conversation:')&&
      !String(preview.parent_agent_path||'').trim();
  });
  const agyIds=[...new Set(agy.map(entry=>String(entry?.source_id||'')).filter(Boolean))];
  if(agyIds.length!==1)return null;
  return aggregate(agy.filter(entry=>String(entry?.source_id||'')===agyIds[0]));
}
'''
new = '''function canonicalRootRecord(){
  const roots=entries.filter(entryHasRootAuthority);
  const sourceIds=[...new Set(roots.map(entry=>String(entry?.source_id||'')).filter(Boolean))];
  if(sourceIds.length!==1){
    if(sourceIds.length)return null;
    const agy=entries.filter(entry=>{
      const preview=entry?.conversation_preview;
      return String(entry?.provider||'').toLowerCase()==='antigravity'&&!!preview&&
        String(entry?.source_id||'').startsWith('agent:antigravity:conversation:')&&
        !String(preview.parent_agent_path||'').trim();
    });
    const agyIds=[...new Set(agy.map(entry=>String(entry?.source_id||'')).filter(Boolean))];
    if(agyIds.length===1)return aggregate(agy.filter(entry=>String(entry?.source_id||'')===agyIds[0]));
  }
  if(sourceIds.length!==1)return null;
  return aggregate(roots.filter(entry=>String(entry?.source_id||'')===sourceIds[0]));
}
'''
if text.count(old) != 1:
    raise SystemExit(f"canonical root compatibility guard failed: {text.count(old)}")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
