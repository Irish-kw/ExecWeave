"""Export a node-by-node replay using the Dashboard's real rendered SVG geometry."""

GIF_SCRIPT = r"""
const gifSvg=document.getElementById('svg');
const gifNotice=document.createElement('span');
gifNotice.id='gif-notice';gifNotice.setAttribute('role','status');
gifNotice.style.cssText='font-size:11px;color:var(--muted);max-width:230px';
finishedActions.appendChild(gifNotice);
const gifScope="Graph viewport only. Exports a node-by-node topology replay using this Dashboard's real node positions, labels, edge paths, folding, theme, and camera.";
gifButton.title=gifScope;
gifButton.setAttribute('aria-description',gifScope);
const GIF_MAX_BYTES=64*1024*1024,GIF_FINAL_HOLD_MS=900;
let gifExporting=false;

const gifProperties=[
  'color','fill','fill-opacity','fill-rule','stroke','stroke-width','stroke-opacity',
  'stroke-dasharray','stroke-dashoffset','stroke-linecap','stroke-linejoin',
  'stroke-miterlimit','paint-order','opacity','display','visibility','filter',
  'font-family','font-size','font-weight','font-style','font-stretch','letter-spacing',
  'word-spacing','text-anchor','dominant-baseline','text-transform','text-rendering',
  'white-space','transform','transform-origin','transform-box','vector-effect',
  'marker-start','marker-mid','marker-end','clip-path','rx','ry'
];

function observeGifPayload(_data){}
function captureGifFrame(_force=false){return null;}

function gifEdgeId(edge){
  return edge?.id||`${edge?.source||''}:${edge?.relation||''}:${edge?.target||''}`;
}
function gifStableCompare(a,b){return a<b?-1:a>b?1:0;}
function gifMoment(item){
  const sequence=Number.isSafeInteger(item?.first_sequence)&&item.first_sequence>=0?item.first_sequence:null;
  const parsed=Date.parse(String(item?.first_seen||item?.timestamp||''));
  return{sequence,time:Number.isFinite(parsed)?parsed:null};
}
function gifOrderedEvents(nodes,edges){
  const events=[
    ...edges.map(edge=>({kind:'edge',id:gifEdgeId(edge),item:edge,...gifMoment(edge)})),
    ...nodes.map(node=>({kind:'node',id:node.id,item:node,...gifMoment(node)})),
  ];
  const tie=(a,b)=>(a.kind===b.kind?0:a.kind==='edge'?-1:1)||gifStableCompare(a.id,b.id);
  const byTime=(a,b)=>((a.time??Infinity)-(b.time??Infinity))||tie(a,b);
  const sequenced=events.filter(event=>event.sequence!==null)
    .sort((a,b)=>a.sequence-b.sequence||byTime(a,b));
  // Sequence is authoritative even under clock skew. Insert timestamp-only
  // observations between monotone sequence/time anchors; do not use a pairwise
  // sequence-or-time comparator, which can form cycles and depend on input order.
  const clock=[];let latest=-Infinity;
  for(const event of sequenced){latest=Math.max(latest,event.time??-Infinity);clock.push(latest);}
  const buckets=Array.from({length:sequenced.length+1},()=>[]);
  for(const event of events){
    if(event.sequence!==null)continue;
    let lo=0,hi=clock.length;
    if(event.time===null)lo=hi;
    else while(lo<hi){const mid=(lo+hi)>>1;if(clock[mid]<=event.time)lo=mid+1;else hi=mid;}
    buckets[lo].push(event);
  }
  const ordered=[];
  for(let i=0;i<buckets.length;i++){
    for(const event of buckets[i].sort(byTime))ordered.push(event);
    if(i<sequenced.length)ordered.push(sequenced[i]);
  }
  return ordered;
}
function gifTopologySteps(graph){
  const nodes=[...(graph?.nodes||[])].filter(node=>node?.id);
  const nodeIds=new Set(nodes.map(node=>node.id));
  const edges=[...(graph?.edges||[])]
    .filter(edge=>edge&&nodeIds.has(edge.source)&&nodeIds.has(edge.target));
  const seenNodes=new Set(),seenEdges=new Set(),steps=[];
  const pushNode=nodeId=>{
    if(!nodeId||seenNodes.has(nodeId)||!nodeIds.has(nodeId))return;
    seenNodes.add(nodeId);steps.push({nodeId,edgeId:null});
  };
  const pushEdge=edge=>{
    const id=gifEdgeId(edge);
    if(!id||seenEdges.has(id))return;
    if(!seenNodes.has(edge.source))pushNode(edge.source);
    if(!seenNodes.has(edge.target)){
      seenNodes.add(edge.target);seenEdges.add(id);
      steps.push({nodeId:edge.target,edgeId:id});return;
    }
    seenEdges.add(id);steps.push({nodeId:null,edgeId:id});
  };
  const ordered=gifOrderedEvents(nodes,edges);
  // Only explicit root identity establishes initial context; do not guess that
  // an arbitrary disconnected node or the first edge's source is the root.
  const roots=nodes.filter(node=>node.type==='agent'&&
    (node.attributes?.agent_path==='/root'||node.agent_path==='/root'||node.name==='/root'));
  const rootIds=new Set(roots.map(node=>node.id));
  for(const event of ordered)if(event.kind==='node'&&rootIds.has(event.id))pushNode(event.id);
  for(const event of ordered){if(event.kind==='edge')pushEdge(event.item);else pushNode(event.id);}
  return steps;
}
function gifStepDelayMs(stepCount){
  if(stepCount<=1)return GIF_FINAL_HOLD_MS;
  return Math.max(90,Math.min(180,Math.round(7000/Math.max(1,stepCount))));
}
function gifSnapshot(visibleNodeIds=null,visibleEdgeIds=null){
  const box=gifSvg.getBoundingClientRect();
  const width=Math.round(box.width),height=Math.round(box.height);
  if(!width||!height)return null;
  const clone=gifSvg.cloneNode(true);
  const originals=[gifSvg,...gifSvg.querySelectorAll('*')];
  const copies=[clone,...clone.querySelectorAll('*')];
  const styles=new Map(),remove=[];
  for(let i=0;i<originals.length;i++){
    const original=originals[i],copy=copies[i],classes=original.classList;
    const nodeId=classes?.contains('node')?original.dataset.id:null;
    const edgeElement=classes?.contains('edge')||classes?.contains('edge-hit')||classes?.contains('label');
    const edgeId=edgeElement?original.dataset.edgeId:null;
    if(visibleNodeIds&&nodeId&&!visibleNodeIds.has(nodeId))remove.push(copy);
    if(visibleEdgeIds&&edgeId&&!visibleEdgeIds.has(edgeId))remove.push(copy);

    const computed=getComputedStyle(original);
    // Routing metadata can contain NUL-delimited keys. Keep only the two identifiers
    // needed to filter replay frames; all other data/ARIA attributes are non-visual.
    for(const attribute of [...copy.attributes]){
      const keepReplayId=attribute.name==='data-id'||attribute.name==='data-edge-id';
      if((attribute.name.startsWith('data-')&&!keepReplayId)||attribute.name.startsWith('aria-')){
        copy.removeAttribute(attribute.name);
      }
    }
    copy.removeAttribute('style');
    for(const property of gifProperties){
      const value=computed.getPropertyValue(property)
        .replace(/url\(["']?[^)"']*#([^)"' ]+)["']?\)/g,'url(#$1)');
      if(value)copy.style.setProperty(property,value);
    }
    // Freeze the rendered appearance. The GIF is a topology replay, not a replay of
    // CSS animations restarting on each decoded SVG.
    copy.style.setProperty('animation','none');copy.style.setProperty('transition','none');
    const css=copy.style.cssText;
    if(!styles.has(css))styles.set(css,`execweave-gif-style-${styles.size}`);
    copy.removeAttribute('style');copy.classList.add(styles.get(css));
  }
  for(const copy of remove)copy.remove();

  clone.setAttribute('xmlns','http://www.w3.org/2000/svg');
  clone.setAttribute('width',width);clone.setAttribute('height',height);
  clone.setAttribute('viewBox',`0 0 ${width} ${height}`);
  const ns='http://www.w3.org/2000/svg';
  const stylesheet=document.createElementNS(ns,'style');
  stylesheet.textContent=[...styles].map(([css,name])=>`.${name}{${css}}`).join('\n');
  clone.insertBefore(stylesheet,clone.firstChild);
  const background=document.createElementNS(ns,'rect');
  background.setAttribute('width',width);background.setAttribute('height',height);
  background.setAttribute('fill',getComputedStyle(document.getElementById('graph-panel')).backgroundColor);
  clone.insertBefore(background,clone.firstChild);
  const defs=document.createElementNS(ns,'defs'),pattern=document.createElementNS(ns,'pattern');
  pattern.id='execweave-gif-paper';pattern.setAttribute('width','22');pattern.setAttribute('height','22');pattern.setAttribute('patternUnits','userSpaceOnUse');
  const dot=document.createElementNS(ns,'circle');dot.setAttribute('cx','1');dot.setAttribute('cy','1');dot.setAttribute('r','1');
  dot.setAttribute('fill',`color-mix(in srgb,${getComputedStyle(gifSvg).getPropertyValue('--border')} 52%,transparent)`);
  pattern.appendChild(dot);defs.appendChild(pattern);clone.insertBefore(defs,background);
  const paper=background.cloneNode();paper.setAttribute('fill','url(#execweave-gif-paper)');background.after(paper);
  return{svg:new XMLSerializer().serializeToString(clone),width,height,element:clone};
}
function gifReplaySnapshot(base,visibleNodeIds,visibleEdgeIds){
  // Freeze geometry, camera, filtering, labels and theme once per export. A UI
  // update during asynchronous rasterization must never rewrite later frames.
  const clone=base.element.cloneNode(true);
  for(const node of clone.querySelectorAll('.node[data-id]')){
    if(!visibleNodeIds.has(node.getAttribute('data-id')))node.remove();
  }
  for(const edge of clone.querySelectorAll('.edge[data-edge-id],.edge-hit[data-edge-id],.label[data-edge-id]')){
    if(!visibleEdgeIds.has(edge.getAttribute('data-edge-id')))edge.remove();
  }
  return{svg:new XMLSerializer().serializeToString(clone),width:base.width,height:base.height};
}

function pushWord(out,value){out.push(value&255,(value>>8)&255);}
function pushText(out,text){for(let i=0;i<text.length;i++)out.push(text.charCodeAt(i)&255);}
function gifBlocks(data){
  const out=new Uint8Array(data.length+Math.ceil(data.length/255)+1);
  let source=0,target=0;
  while(source<data.length){const size=Math.min(255,data.length-source);out[target++]=size;out.set(data.subarray(source,source+size),target);source+=size;target+=size;}
  return out;
}
function lzw(indices){
  const clear=256,end=257,out=[],dictionary=new Map();
  let next=258,size=9,buffer=0,bits=0;
  const emit=code=>{buffer|=code<<bits;bits+=size;while(bits>=8){out.push(buffer&255);buffer>>>=8;bits-=8;}};
  emit(clear);
  if(indices.length){
    let prefix=indices[0];
    for(let i=1;i<indices.length;i++){
      const symbol=indices[i],key=prefix*256+symbol,hit=dictionary.get(key);
      if(hit!==undefined){prefix=hit;continue;}
      emit(prefix);
      if(next<4096){
        dictionary.set(key,next++);
        if(next>(1<<size)&&size<12)size++;
      }else{emit(clear);dictionary.clear();next=258;size=9;}
      prefix=symbol;
    }
    emit(prefix);
    if(next===(1<<size)&&size<12)size++;
  }
  emit(end);if(bits)out.push(buffer&255);return Uint8Array.from(out);
}
function gifPixels(imageData){
  const data=imageData.data,counts=new Uint32Array(32768),rs=new Float64Array(32768),gs=new Float64Array(32768),bs=new Float64Array(32768);
  for(let i=0;i<data.length;i+=4){const key=(data[i]>>3)*1024+(data[i+1]>>3)*32+(data[i+2]>>3);counts[key]++;rs[key]+=data[i];gs[key]+=data[i+1];bs[key]+=data[i+2];}
  const colors=[];for(let key=0;key<counts.length;key++)if(counts[key])colors.push(key);
  colors.sort((a,b)=>counts[b]-counts[a]||a-b);
  const palette=new Uint8Array(768),lookup=new Int16Array(32768);lookup.fill(-1);
  const chosen=colors.slice(0,256);
  for(let i=0;i<chosen.length;i++){const k=chosen[i];palette[i*3]=Math.round(rs[k]/counts[k]);palette[i*3+1]=Math.round(gs[k]/counts[k]);palette[i*3+2]=Math.round(bs[k]/counts[k]);lookup[k]=i;}
  for(const k of colors){
    if(lookup[k]>=0)continue;
    const r=rs[k]/counts[k],g=gs[k]/counts[k],b=bs[k]/counts[k];let best=Infinity,index=0;
    for(let j=0;j<chosen.length;j++){const distance=(r-palette[j*3])**2+(g-palette[j*3+1])**2+(b-palette[j*3+2])**2;if(distance<best){best=distance;index=j;}}
    lookup[k]=index;
  }
  const pixels=new Uint8Array(imageData.width*imageData.height);
  for(let i=0,j=0;i<data.length;i+=4,j++)pixels[j]=lookup[(data[i]>>3)*1024+(data[i+1]>>3)*32+(data[i+2]>>3)];
  return{palette,pixels};
}
async function rasterGifFrame(frame,width,height){
  const url=URL.createObjectURL(new Blob([frame.svg],{type:'image/svg+xml;charset=utf-8'}));
  try{
    const image=new Image();image.src=url;await image.decode();
    const canvas=document.createElement('canvas');canvas.width=width;canvas.height=height;
    const ctx=canvas.getContext('2d',{willReadFrequently:true});
    ctx.fillStyle='#0a0f16';ctx.fillRect(0,0,width,height);
    ctx.drawImage(image,0,0,frame.width,frame.height);
    return gifPixels(ctx.getImageData(0,0,width,height));
  }finally{URL.revokeObjectURL(url);}
}
function gifFrameParts(raster,width,height,delayMs){
  let delay=Math.max(2,Math.round(delayMs/10));
  const parts=[];
  do{
    const chunk=Math.min(65535,delay),block=[0x21,0xF9,4,4];pushWord(block,chunk);block.push(0,0,0x2C);
    pushWord(block,0);pushWord(block,0);pushWord(block,width);pushWord(block,height);block.push(0x87);
    parts.push(Uint8Array.from(block),raster.palette,Uint8Array.of(8),gifBlocks(lzw(raster.pixels)));delay-=chunk;
  }while(delay>0);
  return parts;
}
async function downloadGif(){
  if(gifButton.disabled||gifExporting)return;
  if(replaying){gifNotice.textContent='Wait for replay to finish before exporting.';return;}
  const protective=document.getElementById('protective');
  if(protective&&!protective.hidden){gifNotice.textContent='GIF unavailable: graph rendering is paused.';return;}
  const original=gifButton.textContent,replayWasDisabled=replayButton.disabled;
  gifExporting=true;gifButton.disabled=true;replayButton.disabled=true;
  try{
    const graph=core.getDisplayGraph?.()||core.getGraph?.()||{};
    const session=graph.session_id||core.getGraph?.()?.session_id||'run';
    const steps=gifTopologySteps(graph);
    if(!steps.length||!gifSvg.querySelector('.node')){gifNotice.textContent='No visible graph to replay.';return;}
    const base=gifSnapshot();if(!base){gifNotice.textContent='GIF unavailable: graph viewport has no size.';return;}
    if(base.width>65535||base.height>65535){gifNotice.textContent='GIF unavailable: viewport is too large.';return;}
    const visibleNodes=new Set(),visibleEdges=new Set(),stepDelay=gifStepDelayMs(steps.length);
    const header=[];pushText(header,'GIF89a');pushWord(header,base.width);pushWord(header,base.height);header.push(0x70,0,0);
    header.push(0x21,0xFF,0x0B);pushText(header,'NETSCAPE2.0');header.push(3,1,0,0,0);
    const parts=[Uint8Array.from(header)];let encodedBytes=header.length;
    for(let i=0;i<steps.length;i++){
      const step=steps[i];
      if(step.nodeId)visibleNodes.add(step.nodeId);
      if(step.edgeId)visibleEdges.add(step.edgeId);
      gifButton.textContent=`Encoding ${i+1}/${steps.length}`;await sleep(0);
      const frame=gifReplaySnapshot(base,visibleNodes,visibleEdges);
      const raster=await rasterGifFrame(frame,base.width,base.height);
      const frameParts=gifFrameParts(raster,base.width,base.height,i===steps.length-1?GIF_FINAL_HOLD_MS:stepDelay);
      for(const part of frameParts){encodedBytes+=part.byteLength;if(encodedBytes>GIF_MAX_BYTES)throw new Error('topology replay exceeded 64 MB');parts.push(part);}
    }
    parts.push(Uint8Array.of(0x3B));
    const blob=new Blob(parts,{type:'image/gif'}),url=URL.createObjectURL(blob),a=document.createElement('a');
    a.href=url;a.download=`execweave-${session}.gif`;document.body.appendChild(a);a.click();a.remove();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
    gifNotice.textContent=`Saved node-by-node replay (${steps.length} topology steps).`;
  }catch(error){gifNotice.textContent=`GIF export failed: ${error.message}`;}
  finally{gifExporting=false;gifButton.disabled=false;replayButton.disabled=replayWasDisabled;gifButton.textContent=original;}
}
if(typeof window!=='undefined')window.__execweaveGifTopologySteps=gifTopologySteps;
"""
