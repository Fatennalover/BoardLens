// Read board data in the page world.
(()=>{
 const names={pawn:'p',knight:'n',bishop:'b',rook:'r',queen:'q',king:'k'};
 function fenOf(map,turn='w'){
  let rows=[];for(let rank=8;rank;rank--){let row='',empty=0;for(let f=0;f<8;f++){const p=map[String.fromCharCode(97+f)+rank];if(!p)empty++;else{if(empty)row+=empty;empty=0;row+=p}}if(empty)row+=empty;rows.push(row)}return rows.join('/')+' '+turn+' - - 0 1';
 }
 function practicePosition(board){
  if(location.hostname!=='lichess.org'||!/^\/analysis(?:\/standard)?(?:\/|$)/.test(location.pathname))return null;
  if(board!==document.querySelector('.analyse__board cg-board'))return null;
  const api=window.lichess?.analysis,ground=window.lichess?.chessground?.(),game=api?.data?.()?.game;
  if(game?.id!=='synthetic'||game.variant?.key!=='standard'||!ground)return null;
  const input=[...document.querySelectorAll('.analyse__underboard .copyables .pair')]
   .find(pair=>pair.querySelector('label')?.textContent.trim()==='FEN')?.querySelector('input.copyable');
  if(!input||document.activeElement===input)return null;
  const fen=input.value.trim(),fields=fen.split(/\s+/);
  if(fields.length!==6||fields[0]!==ground.getFen()||fields[1]!==ground.state.turnColor?.[0])return null;
  return {fen,ground};
 }
 function fullyVisible(rect){
  return rect.width>=150&&rect.height>=150&&rect.left>=0&&rect.top>=0&&rect.right<=innerWidth+1&&rect.bottom<=innerHeight+1;
 }
 function read(){
  if(location.pathname==='/'||location.hostname==='www.chess.com'&&/^\/home\/?$/.test(location.pathname))return [];
  if(document.visibilityState!=='visible')return [];
  return [...document.querySelectorAll('wc-chess-board,cg-board')].filter(e=>fullyVisible(e.getBoundingClientRect())).slice(0,3).map((e,index)=>{
   const rect=e.getBoundingClientRect(),g=e.game;let fen,turnHint=null,bottom=true,points={},exact=false,is3d=!!e.querySelector('canvas');
   const practice=practicePosition(e);
   if(practice){
    fen=practice.fen;exact=true;bottom=practice.ground.state.orientation==='white';
   }else if(g&&typeof g.getFEN==='function'){
    fen=g.getFEN();exact=true;bottom=!(g.getOptions?.()?.flipped??e.closest('.orientation-black'));
    const renderer=g.getRenderer?.(),canvas=e.querySelector('canvas');
    if(is3d&&renderer?.getCoordsFromSquare&&canvas){
     for(let rank=1;rank<=8;rank++)for(let f=0;f<8;f++){const square=String.fromCharCode(97+f)+rank,p=renderer.getCoordsFromSquare(square);points[square]=[p.x/canvas.width,p.y/canvas.height]}
     bottom=points.a1[1]>points.a8[1];
    }
   }else{
    let map={};bottom=!e.closest('.orientation-black');
    for(const piece of e.querySelectorAll('piece')){
     const classes=[...piece.classList],name=Object.keys(names).find(n=>classes.includes(n));if(!name||classes.includes('ghost'))continue;
     const r=piece.getBoundingClientRect();let f=Math.round((r.left-rect.left)/(rect.width/8)),row=Math.round((r.top-rect.top)/(rect.height/8));if(f<0||f>7||row<0||row>7)continue;
     const square=String.fromCharCode(97+(bottom?f:7-f))+(bottom?8-row:row+1),p=names[name];map[square]=classes.includes('white')?p.toUpperCase():p;
    }
    const wrap=e.closest('.cg-wrap')?.parentElement?.parentElement;
    const runningTop=wrap?.querySelector('.rclock-top.running'),runningBottom=wrap?.querySelector('.rclock-bottom.running');
    if(runningTop)turnHint=!bottom;else if(runningBottom)turnHint=bottom;
    if(turnHint===null){
     const last=[...e.querySelectorAll('square.last-move')];
     if(last.length===2){
      const occupied=last.map(square=>{
       const r=square.getBoundingClientRect(),f=Math.round((r.left-rect.left)/(rect.width/8)),row=Math.round((r.top-rect.top)/(rect.height/8));
       return map[String.fromCharCode(97+(bottom?f:7-f))+(bottom?8-row:row+1)];
      }).filter(Boolean);
      if(occupied.length===1)turnHint=occupied[0]===occupied[0].toLowerCase();
     }
    }
    fen=fenOf(map,turnHint===false?'b':'w');
   }
   if(!fen)return null;
   if(!Object.keys(points).length)for(let rank=1;rank<=8;rank++)for(let f=0;f<8;f++)points[String.fromCharCode(97+f)+rank]=[(bottom?f+.5:7.5-f)/8,(bottom?8.5-rank:rank-.5)/8];
   const scope=e.closest('.round__app,.board-layout-main,.board-layout-component')||e.parentElement;
   const resultNode=scope?.querySelector('.game-over-component,.game-over-header-title,.game-over-modal-title,.result-wrap .status');
   const game_result=resultNode&&resultNode.getClientRects().length?resultNode.textContent.trim().slice(0,180):null;
   return {game_result,fen,exact,turn_hint:turnHint,white_bottom:bottom,index,points,rect:{x:rect.x,y:rect.y,width:rect.width,height:rect.height}};
  }).filter(Boolean);
 }
 setInterval(()=>{try{window.postMessage({boardlensRead:true,boards:read()},location.origin)}catch{}},55);
})();
