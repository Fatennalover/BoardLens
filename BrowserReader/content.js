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
  panel.root.title=(value.provider||'Evaluation')+' · White perspective. Drag to move; resize at lower right.';
  const r=panel.root.getBoundingClientRect();if(r.right>innerWidth)panel.root.style.left=Math.max(0,innerWidth-r.width)+'px';if(r.bottom>innerHeight)panel.root.style.top=Math.max(0,innerHeight-r.height)+'px';
  return panel;
 }
 let busy=false,last=0,lastRequested='',view=0;
 function stillCurrent(requested,revision){
  return requested===lastRequested&&revision===view&&document.visibilityState==='visible';
 }
 async function claimMove(offer,index,requested,revision){
  if(!document.hasFocus())return;
  try{
   const result=await chrome.runtime.sendMessage({type:'claim-play',index,id:offer.id,page:offer.page,fen:offer.fen});
   if(result?.play&&stillCurrent(requested,revision)&&document.hasFocus())
    window.postMessage({boardlensPlay:result.play},location.origin);
  }catch{/* The next observation will confirm the move or pause autoplay. */}
 }
 function svg(tag,attributes){
  const node=document.createElementNS(ns,tag);
  for(const [name,value] of Object.entries(attributes))node.setAttribute(name,value);
  return node;
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
 window.addEventListener('message',async event=>{
  if(event.source!==window||event.origin!==location.origin||!event.data?.boardlensRead)return;
  const boards=event.data.boards;if(!Array.isArray(boards)||boards.length>3)return;
  if(document.visibilityState!=='visible'){layer.replaceChildren();clearEvaluations();return}
  const revision=view,requested=JSON.stringify(boards.map(b=>[b.index,b.board_id,b.fen,b.white_bottom,b.practice_id,b.practice_focused]));
  if(requested!==lastRequested){layer.replaceChildren();lastRequested=requested;}
  if(busy)return;busy=true;
  try{
   const response=await chrome.runtime.sendMessage({type:'boards',focused:document.hasFocus(),dashboard:event.data.dashboard===true,boards:boards.map(b=>({index:b.index,board_id:b.board_id,moves:b.moves,game_result:b.game_result,fen:b.fen,exact:b.exact,play_protocol:2,practice_id:b.practice_id,practice_kind:b.practice_kind,practice_white:b.practice_white,practice_focused:b.practice_focused,turn_hint:b.turn_hint,white_bottom:b.white_bottom}))});
   if(!stillCurrent(requested,revision))return;
   if(!response||response.error){if(response?.repair){notice.textContent='BoardLens: '+response.error;notice.hidden=false}if(Date.now()-last>1500){layer.replaceChildren();clearEvaluations()}return}notice.hidden=true;last=Date.now();
   const fragments=[];
   for(const [id,panel] of evalPanels){
    if(response.evaluation_visible===false||!boards.some(b=>b.index===id&&b.board_id===panel.boardId)){
     panel.observer?.disconnect();panel.root.remove();evalPanels.delete(id);
    }
   }
   for(const b of boards){
    const i=b.index,hint=Object.entries(response).find(([k,v])=>k.endsWith(':'+i)&&v.fen===b.fen);if(!hint)continue;
    const offer=hint[1].autoplay_offer;
    if(offer?.page===b.practice_id&&b.practice_focused)
     await claimMove(offer,i,requested,revision);
    if(!stillCurrent(requested,revision))return;
    if(hint[1].evaluation) evaluation(i,b,hint[1].evaluation);
    else if(Object.hasOwn(hint[1],'evaluation')&&evalPanels.has(i)){
     const panel=evalPanels.get(i);panel.observer?.disconnect();panel.root.remove();evalPanels.delete(i);
    }
    for(const m of hint[1].marks||[]){
     const point=b.points[m.square];if(!point)continue;
     const circle=document.createElementNS(ns,'circle'),r=b.rect;
     circle.setAttribute('cx',r.x+point[0]*r.width);circle.setAttribute('cy',r.y+point[1]*r.height);circle.setAttribute('r',r.width/8*(m.kind==='attack'?.12:.36));circle.setAttribute('fill',m.color);circle.setAttribute('fill-opacity',m.kind==='attack'?'.25':'.4');
     if(m.kind!=='attack'){circle.setAttribute('stroke',m.color);circle.setAttribute('stroke-width','2')}
     fragments.push(circle);
    }
    fragments.push(...arrowLayers(b,hint[1]));
   }
   layer.replaceChildren(...fragments);
  }catch(error){if(String(error).includes('context invalidated')){notice.textContent='BoardLens: reload this chess tab to reconnect the reader.';notice.hidden=false}if(Date.now()-last>1500){layer.replaceChildren();clearEvaluations()}}finally{busy=false}
 });
 function releaseBoard(){
  chrome.runtime.sendMessage({type:'boards',focused:false,boards:[]}).catch(()=>{});
 }
 window.addEventListener('blur',()=>{view++;releaseBoard()});
 window.addEventListener('focus',()=>{view++});
 document.addEventListener('visibilitychange',()=>{
  view++;
  layer.replaceChildren();clearEvaluations();
  if(document.visibilityState!=='visible')
   releaseBoard();
 });
})();
