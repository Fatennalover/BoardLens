// Read board data in the page world.
(()=>{
 const names={pawn:'p',knight:'n',bishop:'b',rook:'r',queen:'q',king:'k'};
 function fenOf(map,turn='w'){
  let rows=[];for(let rank=8;rank;rank--){let row='',empty=0;for(let f=0;f<8;f++){const p=map[String.fromCharCode(97+f)+rank];if(!p)empty++;else{if(empty)row+=empty;empty=0;row+=p}}if(empty)row+=empty;rows.push(row)}return rows.join('/')+' '+turn+' - - 0 1';
 }
 const boardIds=new WeakMap();
 const boardSlots=new WeakMap();
 let nextSlot=0;
 function boardId(board,owner){
  let target=boardIds.get(board);
  if(target?.owner!==owner){
   target={owner,id:crypto.randomUUID().replaceAll('-','')};
   boardIds.set(board,target);
  }
  return target.id;
 }
 function lichessAnalysis(board){
  if(location.hostname!=='lichess.org'||!/^\/analysis(?:\/standard)?(?:\/|$)/.test(location.pathname))return null;
  if(board!==document.querySelector('.analyse__board cg-board'))return null;
  const api=window.lichess?.analysis,ground=window.lichess?.chessground?.(),game=api?.data?.()?.game;
  if(game?.id!=='synthetic'||game.variant?.key!=='standard'||!ground)return null;
  const input=[...document.querySelectorAll('.analyse__underboard .copyables .pair')]
   .find(pair=>pair.querySelector('label')?.textContent.trim()==='FEN')?.querySelector('input.copyable');
  if(!input||document.activeElement===input)return null;
  const fen=input.value.trim(),fields=fen.split(/\s+/);
  if(fields.length!==6||fields[0]!==ground.getFen()||fields[1]!==ground.state.turnColor?.[0])return null;
  return {fen,kind:"analysis",api,ground};
 }
 function computerGame(board){
  if(location.hostname!=='www.chess.com'||!/^\/play\/computer(?:\/[A-Za-z0-9_-]+)?\/?$/.test(location.pathname))return null;
  if(board?.localName!=='wc-chess-board')return null;
  const game=board.game,options=game?.getOptions?.();
  if(options?.id!=='play-computer'||game.getVariant?.()!=='chess'||game.getMode?.()?.name!=='playing'||
     !game.isAtEndOfLine?.()||game.isGameOver?.())return null;
  const fen=game.getFEN?.();
  if(typeof fen!=='string')return null;
  return {fen,kind:'computer-bot',game};
 }
 function practicePosition(board){
  return computerGame(board)||lichessAnalysis(board);
 }
 function fullyVisible(rect){
  return rect.width>=150&&rect.height>=150&&rect.left>=0&&rect.top>=0&&rect.right<=innerWidth+1&&rect.bottom<=innerHeight+1;
 }
 function dashboard(){
  const path=location.pathname.replace(/\/$/,'')||'/';
  return path==='/'||(location.hostname==='www.chess.com'&&path==='/home');
 }
 function puzzlePage(){
  return /^\/(?:puzzles|training)(?:\/|$)/.test(location.pathname);
 }
 function read(){
  if(document.visibilityState!=='visible'||dashboard())return [];
  const puzzle=puzzlePage();
  const boards=[...document.querySelectorAll('wc-chess-board,cg-board')];
  if(!boards.length&&puzzle)boards.push(...document.querySelectorAll('chess-board'));
  return boards.filter(e=>fullyVisible(e.getBoundingClientRect())).map(e=>{
   try {
   if(!boardSlots.has(e))boardSlots.set(e,nextSlot++);
   const index=boardSlots.get(e);
   const rect=e.getBoundingClientRect(),g=e.game;let fen,turnHint=null,bottom=true,points={},exact=false,is3d=!!e.querySelector('canvas');
   const practice=practicePosition(e);
   let gameFen;
   try{gameFen=g?.getFEN?.()}catch{}
   if(practice?.kind==='analysis'){
    fen=practice.fen;exact=true;bottom=practice.ground.state.orientation==='white';
   }else if(typeof gameFen==='string'&&gameFen){
    fen=gameFen;exact=true;bottom=!(g.getOptions?.()?.flipped??(e.closest('.orientation-black,.flipped')||(e.shadowRoot||e).querySelector('.board.flipped')));
    const renderer=g.getRenderer?.(),canvas=e.querySelector('canvas');
    if(is3d&&renderer?.getCoordsFromSquare&&canvas){
     for(let rank=1;rank<=8;rank++)for(let f=0;f<8;f++){const square=String.fromCharCode(97+f)+rank,p=renderer.getCoordsFromSquare(square);points[square]=[p.x/canvas.width,p.y/canvas.height]}
     bottom=points.a1[1]>points.a8[1];
    }
   }else{
    const map={};
    const tiles=e.shadowRoot||e;
    bottom=!e.closest('.orientation-black,.flipped')&&!tiles.querySelector('.board.flipped');
    for(const piece of tiles.querySelectorAll('piece')){
     const classes=[...piece.classList],name=Object.keys(names).find(n=>classes.includes(n));if(!name||classes.includes('ghost'))continue;
     const r=piece.getBoundingClientRect();let f=Math.round((r.left-rect.left)/(rect.width/8)),row=Math.round((r.top-rect.top)/(rect.height/8));if(f<0||f>7||row<0||row>7)continue;
     const square=String.fromCharCode(97+(bottom?f:7-f))+(bottom?8-row:row+1),p=names[name];map[square]=classes.includes('white')?p.toUpperCase():p;
    }
    for(const piece of tiles.querySelectorAll('.piece[class*="square-"]:not(.ghost)')){
     const classes=[...piece.classList];
     const symbol=classes.find(value=>/^[wb][kqrbnp]$/.test(value));
     const square=classes.find(value=>/^square-[1-8]{2}$/.test(value));
     if(!symbol||!square)continue;
     const cell=String.fromCharCode(96+Number(square[7]))+square[8];
     map[cell]=symbol[0]==='w'?symbol[1].toUpperCase():symbol[1];
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
    if(turnHint===null&&puzzle)turnHint=bottom;
    fen=fenOf(map,turnHint===false?'b':'w');
   }
   if(!fen)return null;
   const projected=Object.keys(points).length>0;
   if(!projected)for(let rank=1;rank<=8;rank++)for(let f=0;f<8;f++)points[String.fromCharCode(97+f)+rank]=[(bottom?f+.5:7.5-f)/8,(bottom?8.5-rank:rank-.5)/8];
   const scope=e.closest('.round__app,.board-layout-main,.board-layout-component')||e.parentElement;
   const resultNode=scope?.querySelector('.game-over-component,.game-over-header-title,.game-over-modal-title,.result-wrap .status');
   const resultText=resultNode&&resultNode.getClientRects().length?resultNode.textContent.trim().slice(0,180):null;
   const finished=exact&&g?.isAtEndOfLine?.()&&g.isGameOver?.();
   const game_result=resultText||(finished?'Game over':null);
   const id=boardId(e,practice?.game||practice?.api||g||location.pathname);
   const sans=exact?g?.getHistorySANs?.():null;
   const moves=Array.isArray(sans)&&sans.length<=600?sans:undefined;
   return {game_result,fen,exact,board_id:id,moves,practice_id:practice?boardId(e,practice.game||practice.api):null,practice_kind:practice?.kind,practice_focused:!!practice&&document.hasFocus(),turn_hint:turnHint,white_bottom:bottom,index,points,projected,rect:{x:rect.x,y:rect.y,width:rect.width,height:rect.height}};
   } catch {return null}
  }).filter(Boolean);
 }
 function publishBoard(){
  let interval=55;
  try{
   const visible=document.visibilityState==='visible',boards=visible?read():[];
   if(boards.some(board=>board.practice_focused))interval=25;
   window.postMessage({boardlensRead:true,dashboard:visible&&dashboard(),boards},location.origin);
  }catch{}
  setTimeout(publishBoard,interval);
 }
 publishBoard();
})();
