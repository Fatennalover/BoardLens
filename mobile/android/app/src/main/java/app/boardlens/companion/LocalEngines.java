package app.boardlens.companion;
import android.content.Context;
import java.util.*;
import java.util.concurrent.CancellationException;
import java.util.function.BooleanSupplier;

/** All phone engines share validation, prediction and cancellation; no network inference. */
final class LocalEngines implements AutoCloseable {
 record Evaluated(String text,float whiteShare,String badge){}
 interface RecommendationUpdate { void result(PhoneEngine.Result result,boolean rootComplete); }
 private final PhoneEngine stockfish=new PhoneEngine();private final MaiaLocal maia=new MaiaLocal();private final TinyLocal tiny=new TinyLocal();
 private final java.util.function.LongSupplier clock;
 LocalEngines(){this(System::nanoTime);}
 LocalEngines(java.util.function.LongSupplier clock){this.clock=clock;}
 private volatile boolean cancelled;
 private String backend="";
 private void selectBackend(EngineCatalog.Entry selected){
  String next=selected.maia()?"maia":selected.tiny()?"tiny":"uci";
  if(next.equals(backend))return;
  if(!next.equals("maia"))maia.close();
  if(!next.equals("tiny"))tiny.close();
  if(!next.equals("uci"))stockfish.close();
  backend=next;
 }
 void prepare(Context c,PhoneSettings settings,boolean eval)throws Exception{
  if(eval&&!settings.evaluationEnabled())return;
  String id=eval?settings.evaluator():settings.engine();EngineCatalog.Entry engine=EngineCatalog.get(id);
  selectBackend(engine);
  if(!EngineCatalog.ready(c,id))return;
  if(engine.maia())maia.prepare(c,engine.id(),settings.threads());
  else if(!engine.tiny())stockfish.prepare(c,engine.id(),settings,eval);
 }

 private PhoneEngine.Result one(Context c,ChessPosition board,PhoneSettings settings,String id,boolean eval,PhoneEngine.Update update)throws Exception{
  if(cancelled)throw new CancellationException();EngineCatalog.Entry engine=EngineCatalog.get(id);selectBackend(engine);
  if(engine.maia())return maia.search(c,board,engine.id(),settings.rating(),eval?1:settings.moves(),settings.threads()).result();
  if(engine.tiny())return tiny.search(board,engine.id(),Math.max(50,Math.round(settings.seconds()*1000)));
  return stockfish.search(c,board,settings,eval,update,engine.id());
 }
 PhoneEngine.Result recommend(Context c,ChessPosition board,PhoneSettings settings,BooleanSupplier current,RecommendationUpdate update)throws Exception{
  cancelled=false;String id=EngineCatalog.get(settings.engine()).id();
  long started=clock.getAsLong();
  if(!current.getAsBoolean())throw new CancellationException();
  boolean styled=!settings.style().equals("Balanced")&&EngineCatalog.get(id).kind().equals("stockfish");
  PhoneSettings limits=styled?settings.override(Map.of("moves",Math.max(3,settings.moves()))):settings;
  PhoneEngine.Result root=one(c,board,limits,id,false,update==null||styled?null:r->update.result(r,false));
  if(cancelled||!current.getAsBoolean())throw new CancellationException();
  if(styled)root=styleChoices(board,root,settings.style(),settings.moves());
  // The chosen move is complete now. Optional reply searches must never delay
  // its arrows, including when the user has disabled unfinished suggestions.
  if(update!=null)update.result(root,true);
  if(!settings.predict()||settings.predictionPlies()<2||root.lines().isEmpty())return root;
  PhoneEngine.Line first=root.lines().get(0);List<String> pv=new ArrayList<>();ChessPosition next=board;
  for(String move:first.pv()){if(pv.size()>=settings.predictionPlies()||!next.legal().contains(move))break;pv.add(move);next=next.play(move);}
  // Maia makes one main prediction, rather than deepening a search. Its visible
  // thinking-time budget includes that pass and limits further reply passes.
  // Never discard the first move or wait out a timer just to simulate thinking.
  boolean human=EngineCatalog.get(id).policy();
  long until=(human?started:clock.getAsLong())+(long)((human?settings.seconds():settings.predictionSeconds())*1000000000L);
  while(pv.size()<settings.predictionPlies()&&!next.legal().isEmpty()&&clock.getAsLong()<until){
   if(cancelled||!current.getAsBoolean())throw new CancellationException();PhoneEngine.Result reply;
   try{float left=Math.max(.05f,(until-clock.getAsLong())/1_000_000_000f); reply=one(c,next,settings.continuation(left),id,false,null);}catch(CancellationException cancelledSearch){throw cancelledSearch;}catch(Exception optionalPredictionFailed){break;}
   if(reply.lines().isEmpty())break;String move=reply.lines().get(0).move();if(!next.legal().contains(move))throw new java.io.IOException("Engine returned an illegal continuation");pv.add(move);next=next.play(move);
   List<PhoneEngine.Line> intermediate=new ArrayList<>(root.lines());intermediate.set(0,new PhoneEngine.Line(first.move(),first.cp(),first.mate(),first.depth(),new ArrayList<>(pv)));if(update!=null)update.result(new PhoneEngine.Result(root.fen(),root.provider(),intermediate),true);
  }
  List<PhoneEngine.Line> lines=new ArrayList<>(root.lines());lines.set(0,new PhoneEngine.Line(first.move(),first.cp(),first.mate(),first.depth(),pv));return new PhoneEngine.Result(root.fen(),root.provider(),lines);
 }
 private static PhoneEngine.Result styleChoices(ChessPosition board,PhoneEngine.Result result,String style,int count){
  var lines=new ArrayList<>(result.lines());
  if(lines.size()<2)return result;
  var strongest=lines.get(0);
  if(strongest.cp()!=null && strongest.mate()==null){
   int end=1;
   while(end<lines.size()&&lines.get(end).mate()==null&&lines.get(end).cp()!=null
       &&Math.abs(lines.get(end).cp()-strongest.cp())<=45)end++;
   lines.subList(0,end).sort(Comparator.comparingInt((PhoneEngine.Line line)->styleScore(board,line.move(),style)).reversed());
  }
  return new PhoneEngine.Result(result.fen(),result.provider(),List.copyOf(lines.subList(0,Math.min(count,lines.size()))));
 }

 private static int styleScore(ChessPosition board,String move,String style){
  int from=move.charAt(0)-'a'+8*(move.charAt(1)-'1'),to=move.charAt(2)-'a'+8*(move.charAt(3)-'1');
  char piece=Character.toLowerCase(board.b[from]);
  int center=7-(Math.abs(2*(to%8)-7)+Math.abs(2*(to/8)-7))/2;
  boolean capture=board.b[to]!='.',check=board.play(move).inCheck(!board.white);
  return switch(style){
   case "Aggressive" -> (capture?6:0)+(check?8:0)+center;
   case "Defensive" -> (piece=='k'&&Math.abs(from-to)==2?10:0)+(piece=='q'?-3:0)-(capture?2:0);
   case "Human-like" -> (piece=='n'||piece=='b'?4:0)+(capture?3:0)+center;
   default -> 0;
  };
 }
 static Evaluated score(String name,PhoneEngine.Line lead){
  String score=lead.mate()!=null?"M"+lead.mate():lead.cp()!=null?String.format(Locale.ROOT,"%+.2f",lead.cp()/100.):"…";
  float share=lead.mate()!=null?(lead.mate()>0?.99f:.01f):lead.cp()!=null?(float)(1/(1+Math.exp(-Math.max(-1200,Math.min(1200,lead.cp()))/220.))):.5f;
  return new Evaluated(name+" · "+score+" · White’s perspective",share,score);
 }
 Evaluated evaluate(Context c,ChessPosition board,PhoneSettings settings)throws Exception{return evaluate(c,board,settings,null);}
 Evaluated evaluate(Context c,ChessPosition board,PhoneSettings settings,java.util.function.Consumer<Evaluated> update)throws Exception{
  if(!settings.evaluationEnabled()){close();return new Evaluated("Evaluation off",.5f,"Off");}
  cancelled=false;String id=EngineCatalog.get(settings.evaluator()).id();EngineCatalog.Entry engine=EngineCatalog.get(id);
  selectBackend(engine);
  if(engine.maia()){
   MaiaLocal.Prediction prediction=maia.search(c,board,id,settings.rating(),1,settings.threads());String value=String.format(Locale.ROOT,"%.2f",prediction.whiteExpected());
   Evaluated result=new Evaluated(engine.name()+" · human expected score "+value,prediction.whiteExpected(),value+" exp.");if(update!=null)update.accept(result);return result;
  }
  PhoneEngine.Result result=one(c,board,settings,id,true,update==null?null:r->{if(!r.lines().isEmpty())update.accept(score(engine.name(),r.lines().get(0)));});
  if(result.lines().isEmpty())return new Evaluated("No evaluation",.5f,"…");return score(engine.name(),result.lines().get(0));
 }
 void cancel(){cancelled=true;stockfish.cancel();maia.cancel();tiny.cancel();}
 public void close(){cancel();stockfish.close();maia.close();tiny.close();backend="";}
}
