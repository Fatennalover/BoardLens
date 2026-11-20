package app.boardlens.companion;
import android.app.*;
import android.content.*;
import android.os.*;
import android.view.*;
import android.widget.*;
import java.util.*;

public final class ModelsActivity extends Activity {
 private MobileUi ui;private final Map<String,Button> buttons=new HashMap<>();private TextView state;private boolean checking;
 @Override public void onCreate(Bundle saved){super.onCreate(saved);ui=new MobileUi(this);ScrollView root=new ScrollView(this);root.setBackgroundColor(MobileUi.BG);LinearLayout col=ui.column();col.setPadding(ui.dp(20),ui.dp(12),ui.dp(20),ui.dp(24));root.addView(col);
  col.addView(ui.button("‹ Phone analysis",false,this::finish),new LinearLayout.LayoutParams(-1,ui.dp(48)));ui.gap(col,16);col.addView(ui.text("Engine library",26,MobileUi.FG,true));ui.gap(col,8);col.addView(ui.text("Choose which models to run on this phone.",14,MobileUi.MUTED,false));ui.gap(col,14);
  state=ui.text("",14,MobileUi.ACCENT,false);col.addView(state);
  col.addView(ui.button("Download recommended",true,()->download(new String[]{"stockfish","maia3-5m"})),new LinearLayout.LayoutParams(-1,ui.dp(50)));ui.gap(col,8);
  col.addView(ui.button("Cancel download",false,()->startService(new Intent(this,ModelDownloads.class).setAction("CANCEL"))),new LinearLayout.LayoutParams(-1,ui.dp(48)));ui.gap(col,18);
  col.addView(ui.button("Test installed engines",false,this::check),new LinearLayout.LayoutParams(-1,ui.dp(48)));ui.gap(col,18);
  LinearLayout optional=ui.column();
  for(EngineCatalog.Entry engine:EngineCatalog.ALL){
   if(engine.tiny()||engine.id().equals("flounder"))continue;
   LinearLayout card=ui.card();
   card.addView(ui.text(engine.name(),18,MobileUi.FG,true));
   ui.gap(card,6);card.addView(ui.text(EngineProfiles.summary(this,engine),13,MobileUi.MUTED,false));ui.gap(card,8);
   card.addView(ui.button("Engine details",false,()->EngineProfiles.show(this,engine)),new LinearLayout.LayoutParams(-1,ui.dp(42)));
   Button button=ui.button("",false,()->{
    if(EngineCatalog.ready(this,engine.id()))use(engine.id());else download(new String[]{engine.id()});
   });
   button.setTag("model-"+engine.id());buttons.put(engine.id(),button);card.addView(button,new LinearLayout.LayoutParams(-1,ui.dp(48)));
   LinearLayout section=List.of("stockfish","maia3-5m").contains(engine.id())?col:optional;
   section.addView(card);ui.gap(section,10);
  }
  optional.setVisibility(View.GONE);
  Button more=ui.button("Show more models",false,()->{});
  more.setOnClickListener(unused->{
   boolean show=optional.getVisibility()!=View.VISIBLE;
   optional.setVisibility(show?View.VISIBLE:View.GONE);
   more.setText(show?"Hide extra models":"Show more models");
  });
  col.addView(more,new LinearLayout.LayoutParams(-1,ui.dp(48)));col.addView(optional);
  ui.gap(col,12);
  col.addView(ui.button("Built-in bot profiles",false,this::showBotProfiles),new LinearLayout.LayoutParams(-1,ui.dp(48)));
  MobileUi.inset(this,root);setContentView(root);refresh();
 }
 private void showBotProfiles(){
  List<EngineCatalog.Entry> bots=new ArrayList<>();
  for(var engine:EngineCatalog.ALL)if(engine.tiny()||engine.id().equals("flounder"))bots.add(engine);
  String[] names=bots.stream().map(EngineCatalog.Entry::name).toArray(String[]::new);
  new AlertDialog.Builder(this).setTitle("Built-in bot profiles")
      .setItems(names,(dialog,index)->EngineProfiles.show(this,bots.get(index)))
      .setNegativeButton("Close",null).show();
 }
 private void use(String id){new PhoneSettings(this).p.edit().putString("engine",id).putLong("analysis_request",SystemClock.elapsedRealtimeNanos()).apply();Toast.makeText(this,EngineCatalog.get(id).name()+" selected for moves",Toast.LENGTH_SHORT).show();finish();}
 private void check(){if(checking)return;if(ScreenService.running){Toast.makeText(this,"Stop screen analysis before running engine checks",Toast.LENGTH_LONG).show();return;}checking=true;state.setText("Checking installed engines…");EngineCheck.run(this,text->runOnUiThread(()->{if(!isFinishing()&&!isDestroyed())state.setText(text);}),result->runOnUiThread(()->{checking=false;if(!isFinishing()&&!isDestroyed()){state.setText("Engine check complete");new AlertDialog.Builder(this).setTitle("Engine check").setMessage(result).setPositiveButton("Done",null).show();}}));}
 private void download(String[] models){ArrayList<String> ids=new ArrayList<>();for(String id:models)if(!EngineCatalog.ready(this,id))ids.add(id);if(ids.isEmpty()){Toast.makeText(this,"Already installed",Toast.LENGTH_SHORT).show();return;}startForegroundService(new Intent(this,ModelDownloads.class).putStringArrayListExtra("models",ids));}
 private void refresh(){if(isFinishing())return;state.setText(ModelDownloads.message);for(var entry:buttons.entrySet()){boolean ready=EngineCatalog.ready(this,entry.getKey());Button b=entry.getValue();b.setText(ready?(EngineCatalog.get(new PhoneSettings(this).engine()).id().equals(entry.getKey())?"Using for moves":"Use for moves"):ModelDownloads.current.equals(entry.getKey())?"Downloading · "+ModelDownloads.progress+"%":"Download · "+(entry.getKey().equals("stockfish")?"99 MB":PhoneModels.size(this,entry.getKey())));b.setEnabled(!ModelDownloads.current.equals(entry.getKey()));}}
 @Override public void onResume(){super.onResume();ModelDownloads.listener=this::refresh;refresh();}
 @Override public void onPause(){ModelDownloads.listener=null;super.onPause();}
  @Override protected void onStart(){super.onStart();PhoneUiVisibility.start(this);}
  @Override protected void onStop(){PhoneUiVisibility.stop(this);super.onStop();}

}
