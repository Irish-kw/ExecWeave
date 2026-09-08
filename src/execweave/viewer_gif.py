"""Record the displayed SVG, rather than inventing history from the final graph."""

GIF_SCRIPT = r"""
const gifSvg=document.getElementById('svg');
const gifNotice=document.createElement('span');
gifNotice.id='gif-notice';gifNotice.setAttribute('role','status');
gifNotice.style.cssText='font-size:11px;color:var(--muted);max-width:230px';
finishedActions.appendChild(gifNotice);
const gifScope='Graph viewport only, at screen resolution. Records this page while it is visible; reopening a finished run exports a still image.';
gifButton.title=gifScope;
gifButton.setAttribute('aria-description',gifScope);
// Keep actual display states, including folding, labels, edge routing and camera.
// Never discard old states silently to meet a frame or memory cap.
const GIF_INTERVAL=100,GIF_MAX_BYTES=64*1024*1024;
const gifHistory=[];
let gifSnapshotOnly=!!window.__execweaveStaticMode;
let gifBytes=0,gifSession=null,gifFailure='',gifExporting=false,gifLastSample=0,gifLastSvg='',gifEpoch=0;
let gifDirty=true;
const gifObserver=new MutationObserver(()=>{gifDirty=true;});
gifObserver.observe(gifSvg,{subtree:true,childList:true,attributes:true,characterData:true});
gifObserver.observe(document.documentElement,{attributes:true,attributeFilter:['data-theme']});
const gifResizeObserver=new ResizeObserver(()=>{gifDirty=true;});
gifResizeObserver.observe(gifSvg);
const gifProperties=[
  'color','fill','fill-opacity','fill-rule','stroke','stroke-width','stroke-opacity',
  'stroke-dasharray','stroke-dashoffset','stroke-linecap','stroke-linejoin',
  'stroke-miterlimit','paint-order','opacity','display','visibility','filter',
  'font-family','font-size','font-weight','font-style','font-stretch','letter-spacing',
  'word-spacing','text-anchor','dominant-baseline','text-transform','text-rendering',
  'white-space','transform','transform-origin','transform-box','vector-effect',
  'marker-start','marker-mid','marker-end','clip-path','rx','ry'
];
function gifError(message){
  gifFailure=message;gifNotice.textContent=message;gifButton.disabled=true;
}
function observeGifPayload(data){
  if(!gifHistory.length&&data.live_finished)gifSnapshotOnly=true;
  if(!data.live_finished&&core.getGraph()?.session_id!==gifSession)gifSnapshotOnly=false;
}
function gifSnapshot(){
  const box=gifSvg.getBoundingClientRect();
  const width=Math.round(box.width),height=Math.round(box.height);
  if(!width||!height)return null;
  const clone=gifSvg.cloneNode(true);
  const originals=[gifSvg,...gifSvg.querySelectorAll('*')];
  const copies=[clone,...clone.querySelectorAll('*')];
  const styles=new Map();
  for(let i=0;i<originals.length;i++){
    const computed=getComputedStyle(originals[i]),copy=copies[i];
    // Routing metadata contains NUL-delimited bundle keys, legal in HTML DOM
    // attributes but not XML. It has no visual role once styles are frozen.
    for(const attribute of [...copy.attributes]){
      if(attribute.name.startsWith('data-')||attribute.name.startsWith('aria-'))copy.removeAttribute(attribute.name);
    }
    copy.removeAttribute('style');
    for(const property of gifProperties){
      const value=computed.getPropertyValue(property).replace(/url\(["']?[^)"']*#([^)'" ]+)["']?\)/g,'url(#$1)');
      if(value)copy.style.setProperty(property,value);
    }
    // Freeze the sampled appearance; animations must not restart when decoded.
    copy.style.setProperty('animation','none');copy.style.setProperty('transition','none');
    const css=copy.style.cssText;
    if(!styles.has(css))styles.set(css,`execweave-gif-style-${styles.size}`);
    copy.removeAttribute('style');copy.classList.add(styles.get(css));
  }
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
  // The graph's dotted paper is CSS on #wrap, outside the SVG itself.
  const defs=document.createElementNS(ns,'defs'),pattern=document.createElementNS(ns,'pattern');
  pattern.id='execweave-gif-paper';pattern.setAttribute('width','22');pattern.setAttribute('height','22');pattern.setAttribute('patternUnits','userSpaceOnUse');
  const dot=document.createElementNS(ns,'circle');dot.setAttribute('cx','1');dot.setAttribute('cy','1');dot.setAttribute('r','1');
  dot.setAttribute('fill',`color-mix(in srgb,${getComputedStyle(gifSvg).getPropertyValue('--border')} 52%,transparent)`);
  pattern.appendChild(dot);defs.appendChild(pattern);clone.insertBefore(defs,background);
  const paper=background.cloneNode();paper.setAttribute('fill','url(#execweave-gif-paper)');background.after(paper);
  return{svg:new XMLSerializer().serializeToString(clone),width,height,time:performance.now()};
}
function captureGifFrame(force=false){
  if(gifExporting||replaying)return;
  const graph=core.getGraph(),session=graph?.session_id;
  if(!session)return;
  if(session!==gifSession){gifHistory.length=0;gifBytes=0;gifSession=session;gifFailure='';gifLastSvg='';gifEpoch++;gifNotice.textContent='';gifButton.disabled=false;}
  if(gifFailure||!gifSvg.querySelector('.node'))return;
  if(document.hidden){gifError('GIF unavailable: this page was hidden during recording.');return;}
  const protective=document.getElementById('protective');
  if(protective&&!protective.hidden){gifError('GIF unavailable: graph rendering was paused.');return;}
  const now=performance.now();
  if(!force&&now-gifLastSample<GIF_INTERVAL)return;
  if(!force&&!gifDirty&&!gifSvg.getAnimations({subtree:true}).some(a=>a.playState==='running'))return;
  gifLastSample=now;
  try{
    const frame=gifSnapshot();if(!frame)return;
    gifDirty=false;
    if(gifHistory.length&&frame.svg===gifLastSvg)return;
    gifLastSvg=frame.svg;
    const raw=new Blob([frame.svg],{type:'image/svg+xml;charset=utf-8'}),bytes=raw.size;
    if(gifBytes+bytes>GIF_MAX_BYTES){gifError('GIF unavailable: recording exceeded 64 MB.');return;}
    delete frame.svg;
    const epoch=gifEpoch;
    // Compress immutable snapshots, never drop historical frames. Account for
    // in-flight uncompressed bytes too, so a slow compressor cannot grow a queue.
    frame.data=(async()=>{
      if(typeof CompressionStream==='undefined')return raw;
      try{
        const compressed=await new Response(raw.stream().pipeThrough(new CompressionStream('gzip'))).blob();
        frame.compressed=true;if(epoch===gifEpoch)gifBytes+=compressed.size-bytes;
        return compressed;
      }catch(_){return raw;}
    })();
    gifHistory.push(frame);gifBytes+=bytes;
  }catch(error){gifError(`GIF unavailable: ${error.message}`);}
}
// Sample painted frames, not network events: camera motion and user layout changes
// also matter. Stop sampling when the page closes; background gaps are explicit.
let gifAnimationFrame=0;
function sampleGif(){if(!gifSnapshotOnly)captureGifFrame();gifAnimationFrame=requestAnimationFrame(sampleGif);}
gifAnimationFrame=requestAnimationFrame(sampleGif);
window.addEventListener('pagehide',()=>{cancelAnimationFrame(gifAnimationFrame);gifObserver.disconnect();gifResizeObserver.disconnect();});
document.addEventListener('visibilitychange',()=>{
  if(document.hidden&&gifHistory.length&&!finishedShown)gifError('GIF unavailable: this page was hidden during recording.');
});

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
        // The decoder adds each entry one emitted code later than the encoder.
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
  // A local palette preserves dark backgrounds and small colored/text details;
  // the old six-level cube quantized most of the dashboard to black.
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
  let data=await frame.data;
  if(frame.compressed)data=await new Response(data.stream().pipeThrough(new DecompressionStream('gzip'))).blob();
  const url=URL.createObjectURL(new Blob([data],{type:'image/svg+xml;charset=utf-8'}));
  try{
    const image=new Image();image.src=url;await image.decode();
    const canvas=document.createElement('canvas');canvas.width=width;canvas.height=height;
    const ctx=canvas.getContext('2d',{willReadFrequently:true});
    ctx.fillStyle='#0a0f16';ctx.fillRect(0,0,width,height);
    // Resizes are letterboxed at original pixel size, never re-laid out or scaled.
    ctx.drawImage(image,0,0,frame.width,frame.height);
    return gifPixels(ctx.getImageData(0,0,width,height));
  }finally{URL.revokeObjectURL(url);}
}
async function downloadGif(){
  if(gifButton.disabled||gifExporting)return;
  if(replaying){gifNotice.textContent='Wait for replay to finish before exporting.';return;}
  if(gifSnapshotOnly){gifHistory.length=0;gifBytes=0;gifLastSvg='';gifEpoch++;}
  captureGifFrame(true);if(gifFailure)return;
  if(!gifHistory.length){gifNotice.textContent='No visible graph recorded yet.';return;}
  const frames=gifHistory.slice(),session=gifSession;
  const stop=performance.now();
  const width=Math.max(...frames.map(f=>f.width)),height=Math.max(...frames.map(f=>f.height));
  if(width>65535||height>65535){gifError('GIF unavailable: viewport is too large.');return;}
  gifExporting=true;gifButton.disabled=true;replayButton.disabled=true;
  const original=gifButton.textContent;
  try{
    const header=[];pushText(header,'GIF89a');pushWord(header,width);pushWord(header,height);header.push(0x70,0,0);
    header.push(0x21,0xFF,0x0B);pushText(header,'NETSCAPE2.0');header.push(3,1,0,0,0);
    const parts=[Uint8Array.from(header)];let previousEnd=0;
    for(let i=0;i<frames.length;i++){
      gifButton.textContent=`Encoding ${i+1}/${frames.length}`;await sleep(0);
      const raster=await rasterGifFrame(frames[i],width,height);
      const end=Math.round(((frames[i+1]?.time??stop)-frames[0].time)/10);
      let delay=Math.max(2,end-previousEnd);previousEnd+=delay;
      // GIF's delay field is 16-bit centiseconds; preserve long idle intervals.
      do{
        const chunk=Math.min(65535,delay),block=[0x21,0xF9,4,4];pushWord(block,chunk);block.push(0,0,0x2C);
        pushWord(block,0);pushWord(block,0);pushWord(block,width);pushWord(block,height);block.push(0x87);
        parts.push(Uint8Array.from(block),raster.palette,Uint8Array.of(8),gifBlocks(lzw(raster.pixels)));delay-=chunk;
      }while(delay>0);
    }
    parts.push(Uint8Array.of(0x3B));
    const blob=new Blob(parts,{type:'image/gif'}),url=URL.createObjectURL(blob),a=document.createElement('a');
    a.href=url;a.download=`execweave-${session}.gif`;document.body.appendChild(a);a.click();a.remove();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
    gifNotice.textContent=frames.length===1?'Saved current graph (still image).':'Saved recorded graph viewport.';
  }catch(error){gifNotice.textContent=`GIF export failed: ${error.message}`;}
  finally{gifExporting=false;gifButton.disabled=!!gifFailure;replayButton.disabled=false;gifButton.textContent=original;}
}
"""
