(()=>{
 const ns='http://www.w3.org/2000/svg',layer=document.createElementNS(ns,'svg');layer.setAttribute('data-boardlens','arrows');
 Object.assign(layer.style,{position:'fixed',inset:'0',width:'100vw',height:'100vh',pointerEvents:'none',zIndex:'2147483646'});document.documentElement.append(layer);
 const notice=document.createElement('div');notice.hidden=true;Object.assign(notice.style,{position:'fixed',bottom:'12px',left:'12px',zIndex:'2147483647',padding:'9px 12px',borderRadius:'8px',background:'#272036',color:'#fff',font:'13px system-ui',pointerEvents:'none',maxWidth:'320px'});document.documentElement.append(notice);
 const evalPanels=new Map();let savedBars={};chrome.storage.local.get('evaluationBars',v=>{savedBars=v.evaluationBars||{}});
 function clearEvaluations(){for(const panel of evalPanels.values()){panel.observer?.disconnect();panel.root.remove();}evalPanels.clear()}
 function evaluation(index,board,value){
  if(!value)return null;
  let panel=evalPanels.get(index);
  if(!panel){
   const root=document.createElement('div'),label=document.createElement('strong'),track=document.createElement('div'),fill=document.createElement('div'),rotate=document.createElement('button');
   root.setAttribute('data-boardlens','evaluation');root.title='Drag to move · resize from the lower-right corner';
   Object.assign(root.style,{position:'fixed',zIndex:'2147483647',width:'58px',height:'220px',minWidth:'50px',minHeight:'100px',maxWidth:'min(90vw,680px)',maxHeight:'80vh',boxSizing:'border-box',padding:'9px',background:'#211932',color:'#f0e4ff',border:'1px solid #755b9a',borderRadius:'9px',boxShadow:'0 3px 12px #0004',display:'flex',flexDirection:'column',alignItems:'center',gap:'8px',font:'bold 12px system-ui',cursor:'move',userSelect:'none',touchAction:'none',overflow:'hidden'});
   Object.assign(track.style,{position:'relative',width:'20px',flex:'1',background:'#352848',borderRadius:'4px',overflow:'hidden'});Object.assign(fill.style,{position:'absolute',left:'0',right:'0',bottom:'0',height:'50%',background:'#f4ecff',transition:'height 200ms ease-out'});
   label.textContent='…';track.append(fill);root.append(label,track,rotate);document.documentElement.append(root);panel={root,label,fill,share:.5,horizontal:false,boardId:board.board_id};evalPanels.set(index,panel);
   const saved=savedBars[index];root.style.left=(saved?.x??Math.max(4,board.rect.x-68))+'px';root.style.top=(saved?.y??Math.max(4,board.rect.y))+'px';if(saved?.w)root.style.width=saved.w+'px';if(saved?.h)root.style.height=saved.h+'px';
   const setOrientation=horizontal=>{
    panel.horizontal=horizontal;
    root.style.minHeight=horizontal?'42px':'85px';
    root.style.minWidth=horizontal?'130px':'50px';
    root.style.flexDirection=horizontal?'row':'column';
    track.style.width=horizontal?'auto':'20px';
    track.style.height=horizontal?'14px':'auto';
    fill.style.transition=(horizontal?'width':'height')+' 200ms ease-out';
    rotate.textContent=horizontal?'↕':'↔';
    rotate.title=horizontal?'Make evaluation bar vertical':'Make evaluation bar horizontal';
    rotate.setAttribute('aria-label',rotate.title);
    root.style.backgroundImage='linear-gradient(135deg, transparent 50%, #755b9a 50%)';
    root.style.backgroundSize='10px 10px';root.style.backgroundPosition='bottom right';root.style.backgroundRepeat='no-repeat';
   };
   Object.assign(rotate.style,{color:'inherit',background:'transparent',border:'1px solid #755b9a',borderRadius:'4px',padding:'2px 5px',cursor:'pointer',font:'inherit'});
   setOrientation(Boolean(saved?.horizontal));
   let dragging=null,timer;const save=()=>{const r=root.getBoundingClientRect();savedBars[index]={x:r.x,y:r.y,w:r.width,h:r.height,horizontal:panel.horizontal};clearTimeout(timer);timer=setTimeout(()=>chrome.storage.local.set({evaluationBars:savedBars}),180)};
   rotate.onclick=event=>{
    event.stopPropagation();
    const old=root.getBoundingClientRect();
    setOrientation(!panel.horizontal);
    root.style.width=(panel.horizontal?Math.max(185,old.height):Math.max(58,old.height))+'px';
    root.style.height=(panel.horizontal?Math.max(46,old.width):Math.max(170,old.width))+'px';
    save();
   };
   root.addEventListener('pointerdown',event=>{if(event.target===rotate)return;const r=root.getBoundingClientRect();const resize=event.clientX>r.right-18&&event.clientY>r.bottom-18;event.preventDefault();event.stopPropagation();dragging={x:event.clientX,y:event.clientY,left:r.x,top:r.y,w:r.width,h:r.height,resize};root.setPointerCapture(event.pointerId)});
   root.addEventListener('pointermove',event=>{if(!dragging)return;const dx=event.clientX-dragging.x,dy=event.clientY-dragging.y;
    if(dragging.resize){
     root.style.width=Math.min(innerWidth-dragging.left,dragging.w+dx)+'px';
     root.style.height=Math.min(innerHeight-dragging.top,dragging.h+dy)+'px';
    }else{
     root.style.left=Math.max(0,Math.min(innerWidth-root.offsetWidth,dragging.left+dx))+'px';
     root.style.top=Math.max(0,Math.min(innerHeight-root.offsetHeight,dragging.top+dy))+'px';
    }});
   root.addEventListener('pointerup',()=>{dragging=null;save()});root.addEventListener('pointercancel',()=>{dragging=null;save()});panel.observer=new ResizeObserver(save);panel.observer.observe(root);
  }
  const {cp,mate,white_share,score}=value;
  if(typeof cp==='number')panel.share=1/(1+Math.exp(-Math.max(-1200,Math.min(1200,cp))/220));
  if(typeof mate==='number')panel.share=mate>0?.99:.01;
  if(typeof white_share==='number')panel.share=Math.max(0,Math.min(1,white_share));
  panel.fill.style.height=(panel.horizontal?100:panel.share*100)+'%';
  panel.fill.style.width=(panel.horizontal?panel.share*100:100)+'%';
  panel.fill.style.left=panel.horizontal&&!board.white_bottom?'auto':'0';
  panel.fill.style.right=panel.horizontal&&!board.white_bottom?'0':'auto';
  panel.fill.style.bottom=panel.horizontal||board.white_bottom?'0':'auto';
  panel.fill.style.top=panel.horizontal||board.white_bottom?'auto':'0';
  if(typeof mate==='number')panel.label.textContent=(mate>0?'+':'−')+'M'+Math.abs(mate);else if(typeof cp==='number')panel.label.textContent=(cp>=0?'+':'')+(cp/100).toFixed(2);
  if(typeof score==='string'&&score!=='—')panel.label.textContent=score;
  panel.root.title=(value.provider||'Evaluation')+' · '+(value.perspective||'White')+' perspective. Drag to move and resize from the lower-right corner.';
  const r=panel.root.getBoundingClientRect();if(r.right>innerWidth)panel.root.style.left=Math.max(0,innerWidth-r.width)+'px';if(r.bottom>innerHeight)panel.root.style.top=Math.max(0,innerHeight-r.height)+'px';
  return panel;
 }
 let busy=false,last=0,lastRequested='',view=0,pending=null,drawn='';
 function clearArrows(){
  layer.replaceChildren();
  drawn='';
 }
 function stillCurrent(requested,revision){
  return requested===lastRequested&&revision===view&&document.visibilityState==='visible';
 }
 function svg(tag,attributes){
  const node=document.createElementNS(ns,tag);
  for(const [name,value] of Object.entries(attributes))node.setAttribute(name,value);
  return node;
 }
 const labelMetrics=document.createElement('canvas').getContext('2d');
 function markLayers(board, marks){
  const highlights=[],arrows=[],badges=[];
  const {rect,points}=board,cell=rect.width/8;
  function center(square){
   const value=points[square];
   return value&&[rect.x+value[0]*rect.width,rect.y+value[1]*rect.height];
  }
  for(const mark of marks){
   if(mark.kind==='move_score')continue;
   const destination=center(mark.square);
   if(!destination)continue;
   const [x,y]=destination;
   if(mark.kind!=='gain_arrow'){
    const covered=mark.kind==='attack',mate=mark.kind==='mate';
    if(!covered)highlights.push(svg('rect',{x:x-cell/2,y:y-cell/2,width:cell,height:cell,
     fill:mark.color,'fill-opacity':mate?.17:.125}));
    const radius=Math.max(2.2,cell*(covered?.048:.068)),cx=x+cell*.37,cy=y+cell*.37;
    const style={fill:mark.color,stroke:'#21192d','stroke-width':Math.max(.8,cell*.015)};
    highlights.push(mate
     ?svg('polygon',{...style,points:`${cx},${cy-radius} ${cx+radius},${cy} ${cx},${cy+radius} ${cx-radius},${cy}`})
     :svg('circle',{...style,cx,cy,r:radius}));
    continue;
   }
   const origin=center(mark.move?.slice(0,2));
   if(!origin||typeof mark.label!=='string')continue;
   const [sx,sy]=origin,distance=Math.hypot(x-sx,y-sy);
   if(!distance)continue;
   const ux=(x-sx)/distance,uy=(y-sy)/distance;
   const startX=sx+ux*cell*.18,startY=sy+uy*cell*.18;
   const tipX=x-ux*cell*.11,tipY=y-uy*cell*.11;
   const tailX=tipX-ux*cell*.21,tailY=tipY-uy*cell*.21;
   const wx=-uy*cell*.125,wy=ux*cell*.125;
   const d=`M ${startX} ${startY} L ${tailX} ${tailY} M ${tailX+wx} ${tailY+wy} L ${tipX} ${tipY} L ${tailX-wx} ${tailY-wy}`;
   const outline='#1a1527',stroke=Math.max(1.6,cell*.032);
   const path={d,fill:'none','stroke-linecap':'round','stroke-linejoin':'round'};
   arrows.push(svg('path',{...path,stroke:outline,'stroke-width':stroke+2.4}));
   arrows.push(svg('path',{...path,stroke:mark.color,'stroke-width':stroke}));

   const cx=startX+(tipX-startX)*.56,cy=startY+(tipY-startY)*.56;
   const fontSize=Math.max(9,Math.min(17,Math.round(cell*.19)));
   labelMetrics.font=`700 ${fontSize}px system-ui`;
   const width=labelMetrics.measureText(mark.label).width+Math.max(12,cell*.27);
   const height=Math.max(13,fontSize*1.32+3);
   const badge=svg('g',{'data-gain-move':mark.move});
   badge.append(svg('rect',{x:cx-width/2,y:cy-height/2,width,height,rx:height*.31,fill:outline,
    stroke:mark.color,'stroke-width':Math.max(1,cell*.02)}));
   const label=svg('text',{x:cx,y:cy,fill:'#f8f4ff','text-anchor':'middle',
    'dominant-baseline':'central','font-family':'system-ui','font-size':fontSize,'font-weight':700});
   label.textContent=mark.label;
   badge.append(label);
   badges.push(badge);
  }
  return {highlights,gains:[...arrows,...badges]};
 }
 function arrowLayers(board,hint){
  const definitions=svg('defs',{}),base=[],overlaps=[],ids=[];
  const r=board.rect,head=Math.max(10,r.width/28),width=Math.max(4,r.width/85);
  const overlapColor=/^#[0-9a-f]{6}$/i.test(hint.overlap_color||'')?hint.overlap_color:'#a855f7';
  for(const arrow of hint.arrows||[]){
   const from=board.points[arrow.move.slice(0,2)],to=board.points[arrow.move.slice(2,4)];
   if(!from||!to)continue;
   const start=[r.x+from[0]*r.width,r.y+from[1]*r.height];
   const end=[r.x+to[0]*r.width,r.y+to[1]*r.height];
   const angle=Math.atan2(end[1]-start[1],end[0]-start[0]);
   const id=`boardlens-arrow-${board.index}-${ids.length}`;
   const shape=svg('g',{id});
   const line=svg('path',{d:`M ${start.join(' ')} L ${end.join(' ')}`,stroke:'currentColor','stroke-width':width,'stroke-linecap':'round',fill:'none'});
   if(arrow.dashed)line.setAttribute('stroke-dasharray',width*1.6+' '+width);
   const tip=svg('path',{d:`M ${end.join(' ')} L ${end[0]-head*Math.cos(angle-.5)} ${end[1]-head*Math.sin(angle-.5)} L ${end[0]-head*Math.cos(angle+.5)} ${end[1]-head*Math.sin(angle+.5)} Z`,fill:'currentColor'});
   shape.append(line,tip);definitions.append(shape);
   base.push(svg('use',{href:'#'+id,color:arrow.color,opacity:'.85'}));
   if(ids.length){
    const maskId=id+'-overlap';
    const mask=svg('mask',{id:maskId,maskUnits:'userSpaceOnUse',x:r.x,y:r.y,width:r.width,height:r.height});
    for(const previous of ids)mask.append(svg('use',{href:'#'+previous,color:'#ffffff'}));
    definitions.append(mask);
    overlaps.push(svg('use',{href:'#'+id,color:overlapColor,mask:`url(#${maskId})`}));
   }
   ids.push(id);
  }
  return base.length?[definitions,...base,...overlaps]:[];
 }
 window.addEventListener('message',event=>{
  if(event.source!==window||event.origin!==location.origin||!event.data?.boardlensRead)return;
  const {boards}=event.data;
  if(!Array.isArray(boards)||boards.length>3||document.visibilityState!=='visible'||!document.hasFocus())return;
  readBoards(boards,event.data.dashboard===true);
 });
 async function readBoards(boards,dashboard){
  const revision=view,requested=JSON.stringify(boards.map(b=>[b.index,b.board_id,b.fen,b.white_bottom,b.practice_id,b.practice_focused]));
  const coachBoard=boards.find(board=>board.index===0)||boards[0];
  if(requested!==lastRequested){
   clearArrows();lastRequested=requested;
   if(coachBoard)boardLensCoach.update(null);
   else boardLensCoach.clear();
  }
  if(busy){pending={boards,dashboard};return}
  busy=true;
  try{
   const response=await chrome.runtime.sendMessage({type:'boards',focused:true,dashboard,boards:boards.map(b=>({index:b.index,board_id:b.board_id,moves:b.moves,game_result:b.game_result,fen:b.fen,exact:b.exact,practice_id:b.practice_id,practice_kind:b.practice_kind,practice_focused:b.practice_focused,turn_hint:b.turn_hint,white_bottom:b.white_bottom}))});
   if(!stillCurrent(requested,revision))return;
   if(!response||response.error){if(response?.repair){notice.textContent='BoardLens: '+response.error;notice.hidden=false}if(Date.now()-last>1500){clearArrows();clearEvaluations();boardLensCoach.clear()}return}notice.hidden=true;last=Date.now();
   const layers=[];
   let coachHint;
   for(const [id,panel] of evalPanels){
    if(response.evaluation_visible===false||!boards.some(b=>b.index===id&&b.board_id===panel.boardId)){
     panel.observer?.disconnect();panel.root.remove();evalPanels.delete(id);
    }
   }
   for(const b of boards){
    const i=b.index,hint=Object.entries(response).find(([k,v])=>
     k.endsWith(':'+i)&&v.fen===b.fen&&(!Object.hasOwn(v,'board_id')||v.board_id===b.board_id));
    if(!hint)continue;
    if(b===coachBoard)coachHint=hint[1];
    if(hint[1].evaluation) evaluation(i,b,hint[1].evaluation);
    else if(Object.hasOwn(hint[1],'evaluation')&&evalPanels.has(i)){
     const panel=evalPanels.get(i);panel.observer?.disconnect();panel.root.remove();evalPanels.delete(i);
    }
    const {arrows,marks,overlap_color}=hint[1];
    layers.push({board:b,hints:{arrows,marks,overlap_color}});
   }
   const showArrows=boardLensCoach.showArrows;
   const signature=JSON.stringify([showArrows,layers.map(({board,hints})=>[
    board.index,board.board_id,board.rect,board.points,hints
   ])]);
   if(signature!==drawn){
    const fragments=[];
    for(const {board,hints} of layers){
     const {highlights,gains}=markLayers(board,hints.marks||[]);
     fragments.push(...highlights);
     if(showArrows)fragments.push(...arrowLayers(board,hints));
     fragments.push(...gains);
    }
    layer.replaceChildren(...fragments);
    drawn=signature;
   }
   if(coachBoard)boardLensCoach.update(coachHint?.coach, Boolean(coachHint));
   else boardLensCoach.clear();
  }catch(error){
   if(String(error).includes('context invalidated')){
    notice.textContent='BoardLens: reload this chess tab to reconnect the reader.';
    notice.hidden=false;
   }
   if(Date.now()-last>1500){clearArrows();clearEvaluations();boardLensCoach.clear()}
  }finally{
   busy=false;
   const next=pending;
   pending=null;
   if(next&&document.hasFocus()&&document.visibilityState==='visible'){
    readBoards(next.boards,next.dashboard);
   }
  }
 }
 function releaseBoard(){
  view++;
  pending=null;
  lastRequested='';
  clearArrows();
  clearEvaluations();
  boardLensCoach.clear();
  chrome.runtime.sendMessage({type:'boards',focused:false,boards:[]}).catch(()=>{});
 }
 window.addEventListener('blur',releaseBoard);
 window.addEventListener('focus',()=>{view++});
 document.addEventListener('visibilitychange',()=>{
  if(document.visibilityState!=='visible')releaseBoard();
 });
})();
