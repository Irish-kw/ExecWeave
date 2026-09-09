"""Measure routed SVG geometry, not node-center chords, for layout decisions."""

LAYOUT_GEOMETRY_SCRIPT = r"""
const execweaveGeometry=(function(){
  const epsilon=1e-6;
  function polyline(d){
    const tokens=String(d).match(/[A-Za-z]|[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?/g)||[];
    const points=[];let x=0,y=0,i=0,command='';
    while(i<tokens.length){
      if(/^[A-Za-z]$/.test(tokens[i]))command=tokens[i++];
      if(command==='M'||command==='L'){x=Number(tokens[i++]);y=Number(tokens[i++])}
      else if(command==='H')x=Number(tokens[i++]);
      else if(command==='V')y=Number(tokens[i++]);
      else return null;
      if(!Number.isFinite(x)||!Number.isFinite(y))return null;
      points.push({x,y});
    }
    return points;
  }
  const cache=new Map();
  function sample(d){
    if(cache.has(d))return cache.get(d);
    const save=points=>{if(cache.size>=4096)cache.delete(cache.keys().next().value);cache.set(d,points);return points};
    const exact=polyline(d);if(exact)return save(exact);
    // The two intentional special families are measured from the same SVG path
    // string the renderer uses. Browser arc-length sampling handles the cubic.
    const path=document.createElementNS('http://www.w3.org/2000/svg','path');
    path.setAttribute('d',d);const length=path.getTotalLength();
    const count=Math.max(24,Math.min(192,Math.ceil(length/8))),out=[];
    for(let i=0;i<=count;i++){const p=path.getPointAtLength(length*i/count);out.push({x:p.x,y:p.y})}
    return save(out);
  }
  const side=(a,b,c)=>(b.x-a.x)*(c.y-a.y)-(b.y-a.y)*(c.x-a.x);
  function crosses(a,b,c,d){
    if(Math.max(a.x,b.x)<Math.min(c.x,d.x)||Math.max(c.x,d.x)<Math.min(a.x,b.x)||
       Math.max(a.y,b.y)<Math.min(c.y,d.y)||Math.max(c.y,d.y)<Math.min(a.y,b.y))return false;
    const p=side(a,b,c),q=side(a,b,d),r=side(c,d,a),s=side(c,d,b);
    return ((p>epsilon&&q< -epsilon)||(p< -epsilon&&q>epsilon))&&
           ((r>epsilon&&s< -epsilon)||(r< -epsilon&&s>epsilon));
  }
  function throughBox(a,b,box){
    // Liang-Barsky clipping into the OPEN interior. Touching a boundary is not
    // an edge passing through a node. End-node boxes are excluded by the caller.
    let lo=0,hi=1;const dx=b.x-a.x,dy=b.y-a.y;
    const left=box.x+epsilon,right=box.x+box.w-epsilon,top=box.y+epsilon,bottom=box.y+box.h-epsilon;
    for(const [p,q] of [[-dx,a.x-left],[dx,right-a.x],[-dy,a.y-top],[dy,bottom-a.y]]){
      if(Math.abs(p)<epsilon){if(q<0)return false;continue}
      const t=q/p;if(p<0)lo=Math.max(lo,t);else hi=Math.min(hi,t);
      if(lo>=hi)return false;
    }
    return lo<hi&&hi>0&&lo<1;
  }
  function avoidNodes(points,boxes){
    const blocked=(a,b)=>boxes.some(box=>throughBox(a,b,box));
    const inside=p=>boxes.some(b=>p.x>b.x&&p.x<b.x+b.w&&p.y>b.y&&p.y<b.y+b.h);
    // A semantic constraint may move a box over a former Dagre bend. Keep all
    // legal guides, replacing only obstructed bends with visibility detours.
    const guides=points.filter((p,i)=>i===0||i===points.length-1||!inside(p));
    const out=[guides[0]];let detours=0;
    for(let part=1;part<guides.length;part++){
      const a=out[out.length-1],b=guides[part];
      if(!blocked(a,b)){out.push(b);continue}
      let blockers=boxes.filter(box=>throughBox(a,b,box)),found=null;
      for(let pass=0;pass<2&&!found;pass++){
        const vertices=[a,b];
        for(const box of blockers){
          const l=box.x-2,r=box.x+box.w+2,t=box.y-2,d=box.y+box.h+2;
          for(const p of [{x:l,y:t},{x:l,y:d},{x:r,y:t},{x:r,y:d}])if(!inside(p))vertices.push(p);
        }
        const dist=vertices.map(()=>Infinity),prev=vertices.map(()=>-1),used=new Set();dist[0]=0;
        for(let i=0;i<vertices.length;i++){
          let u=-1;for(let j=0;j<vertices.length;j++)if(!used.has(j)&&(u<0||dist[j]<dist[u]))u=j;
          if(u<0||!Number.isFinite(dist[u]))break;
          if(u===1)break;used.add(u);
          for(let v=0;v<vertices.length;v++){
            if(v===u||used.has(v)||blocked(vertices[u],vertices[v]))continue;
            const next=dist[u]+Math.hypot(vertices[u].x-vertices[v].x,vertices[u].y-vertices[v].y);
            if(next<dist[v]-1e-6){dist[v]=next;prev[v]=u}
          }
        }
        if(Number.isFinite(dist[1])){
          found=[];let at=1;while(at>0){found.push(vertices[at]);at=prev[at]}found.reverse();
        }else blockers=boxes;
      }
      if(found){out.push(...found);detours++}else out.push(b);
    }
    return{points:out,detours,obstructedGuides:points.length-guides.length};
  }

  function avoidCrossings(points,boxes,segments,clearance=7){
    const protectedSegments=(Array.isArray(segments)?segments:[]).filter(segment=>
      segment?.a&&segment?.b&&Number.isFinite(segment.a.x)&&Number.isFinite(segment.a.y)&&
      Number.isFinite(segment.b.x)&&Number.isFinite(segment.b.y)&&
      Math.hypot(segment.b.x-segment.a.x,segment.b.y-segment.a.y)>epsilon
    );
    if(!Array.isArray(points)||points.length<2||!protectedSegments.length){
      return{points:Array.isArray(points)?points:[],detours:0,crossingsAvoided:0};
    }
    const nodeBoxes=Array.isArray(boxes)?boxes:[];
    const inside=p=>nodeBoxes.some(box=>p.x>box.x&&p.x<box.x+box.w&&p.y>box.y&&p.y<box.y+box.h);
    const blocked=(a,b)=>nodeBoxes.some(box=>throughBox(a,b,box))||
      protectedSegments.some(segment=>crosses(a,b,segment.a,segment.b));
    const crossingCount=route=>{
      let count=0;
      for(let i=1;i<route.length;i++)for(const segment of protectedSegments)
        if(crosses(route[i-1],route[i],segment.a,segment.b))count++;
      return count;
    };
    const before=crossingCount(points);
    if(!before)return{points,detours:0,crossingsAvoided:0};

    const portals=[];
    for(const segment of protectedSegments){
      const dx=segment.b.x-segment.a.x,dy=segment.b.y-segment.a.y,length=Math.hypot(dx,dy);
      if(length<=epsilon)continue;
      const tx=dx/length,ty=dy/length,nx=-ty,ny=tx;
      for(const endpoint of [segment.a,segment.b])for(const normal of [-1,1])for(const tangent of [-1,1]){
        const p={
          x:endpoint.x+normal*clearance*nx+tangent*clearance*tx,
          y:endpoint.y+normal*clearance*ny+tangent*clearance*ty,
        };
        if(!inside(p))portals.push(p);
      }
    }

    const solve=(a,b,includeBoxes)=>{
      const vertices=[a,b,...portals];
      if(includeBoxes){
        for(const box of nodeBoxes){
          const l=box.x-2,r=box.x+box.w+2,t=box.y-2,d=box.y+box.h+2;
          for(const p of [{x:l,y:t},{x:l,y:d},{x:r,y:t},{x:r,y:d}])if(!inside(p))vertices.push(p);
        }
      }
      const dist=vertices.map(()=>Infinity),prev=vertices.map(()=>-1),used=new Set();dist[0]=0;
      for(let i=0;i<vertices.length;i++){
        let u=-1;for(let j=0;j<vertices.length;j++)if(!used.has(j)&&(u<0||dist[j]<dist[u]))u=j;
        if(u<0||!Number.isFinite(dist[u]))break;
        if(u===1)break;used.add(u);
        for(let v=0;v<vertices.length;v++){
          if(v===u||used.has(v)||blocked(vertices[u],vertices[v]))continue;
          const next=dist[u]+Math.hypot(vertices[u].x-vertices[v].x,vertices[u].y-vertices[v].y);
          if(next<dist[v]-1e-6){dist[v]=next;prev[v]=u}
        }
      }
      if(!Number.isFinite(dist[1]))return null;
      const found=[];let at=1;
      while(at>0){found.push(vertices[at]);at=prev[at]}
      found.reverse();return found;
    };

    const out=[points[0]];let detours=0;
    for(let part=1;part<points.length;part++){
      const a=out[out.length-1],b=points[part];
      const directCrosses=protectedSegments.some(segment=>crosses(a,b,segment.a,segment.b));
      if(!directCrosses){out.push(b);continue}
      const found=solve(a,b,false)||solve(a,b,true);
      if(found){out.push(...found);detours++}else out.push(b);
    }
    const after=crossingCount(out);
    if(after>=before)return{points,detours:0,crossingsAvoided:0};
    return{points:out,detours,crossingsAvoided:before-after};
  }

  function measure(nodes,edges){
    const routes=edges.map(e=>{const points=sample(e.d);return{...e,points,left:Math.min(...points.map(p=>p.x)),right:Math.max(...points.map(p=>p.x)),top:Math.min(...points.map(p=>p.y)),bottom:Math.max(...points.map(p=>p.y))}});
    let crossings=0,overlaps=0,intersections=0;
    for(let i=0;i<nodes.length;i++)for(let j=0;j<i;j++){
      const a=nodes[i],b=nodes[j];
      if(Math.min(a.x+a.w,b.x+b.w)-Math.max(a.x,b.x)>epsilon&&
         Math.min(a.y+a.h,b.y+b.h)-Math.max(a.y,b.y)>epsilon)overlaps++;
    }
    for(let i=0;i<routes.length;i++){
      const a=routes[i];
      for(let j=0;j<i;j++){
        const b=routes[j];if(a.right<b.left||b.right<a.left||a.bottom<b.top||b.bottom<a.top)continue;let hit=false;
        for(let k=1;k<a.points.length&&!hit;k++)for(let l=1;l<b.points.length&&!hit;l++)
          hit=crosses(a.points[k-1],a.points[k],b.points[l-1],b.points[l]);
        if(hit)crossings++;
      }
      for(const node of nodes){
        if(node.id===a.source||node.id===a.target||a.right<=node.x||a.left>=node.x+node.w||a.bottom<=node.y||a.top>=node.y+node.h)continue;
        if(a.points.some((p,k)=>k>0&&throughBox(a.points[k-1],p,node)))intersections++;
      }
    }
    const lengths=routes.map(e=>e.points.reduce((s,p,i)=>i?s+Math.hypot(p.x-e.points[i-1].x,p.y-e.points[i-1].y):s,0)).sort((a,b)=>a-b);
    return{EDGE_CROSSINGS:crossings,NODE_OVERLAPS:overlaps,EDGE_NODE_INTERSECTIONS:intersections,
      MAX_EDGE_LENGTH:lengths.at(-1)||0,P95_EDGE_LENGTH:lengths[Math.max(0,Math.ceil(lengths.length*.95)-1)]||0,
      VISIBLE_NODE_COUNT:nodes.length,VISIBLE_EDGE_COUNT:edges.length};
  }
  return{polyline,sample,crosses,throughBox,measure,avoidNodes,avoidCrossings};
})();
""".strip()
