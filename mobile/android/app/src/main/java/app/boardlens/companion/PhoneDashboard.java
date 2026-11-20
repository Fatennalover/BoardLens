package app.boardlens.companion;

import android.content.Context;
import android.graphics.Bitmap;
import android.view.Gravity;
import android.view.View;
import android.widget.*;

/** Dashboard view shared with the isolated visual preview. */
final class PhoneDashboard {
  interface Actions {
    void start();void stop();void hide();void scan();void settings();void help();void back();
    default String downloadLabel(){return "";}
    default void moves(){}
    default void openFloatingMenu(){}
    default void closeFloatingMenu(){}
    default String timeLabel(){return "Thinking time";}default void timeSettings(){settings();}
    boolean option(String key,boolean fallback);void option(String key,boolean value,boolean unused);
  }
  final ScrollView root;final TextView status,moves,eval,engine;private final TextView downloads;final ImageView preview;
  final ProgressBar bar;final TextView opening;final StudioBoard studioBoard;private final Button start,hide,stop,timing,closeFloating;private final Actions actions;private final MobileUi ui;
  PhoneDashboard(Context c,Actions a){
    actions=a;
    ui=new MobileUi(c);
    root=new ScrollView(c);
    LinearLayout col=ui.page(root);
    col.addView(ui.header("Phone screen","Back to board sources",a::back,a::help));

    LinearLayout navigation=new LinearLayout(c);
    TextView selected=ui.text("Board",15,MobileUi.ACCENT,true);
    selected.setGravity(Gravity.CENTER);
    selected.setBackground(ui.shape(0xff392952,12));
    navigation.addView(selected,new LinearLayout.LayoutParams(0,ui.dp(48),1));
    navButton(navigation,"Moves",a::moves);
    navButton(navigation,"Settings",a::settings);
    ui.gap(col,12);
    col.addView(navigation);
    ui.gap(col,16);

    LinearLayout boardCard=ui.card();
    boardCard.addView(ui.text("Current board",21,MobileUi.FG,true));
    ui.gap(boardCard,8);
    status=ui.text("Ready to start",15,MobileUi.MUTED,false);
    boardCard.addView(status);
    downloads=ui.text("",14,MobileUi.ACCENT,false);
    downloads.setVisibility(View.GONE);
    boardCard.addView(downloads);
    opening=ui.text("",15,ui.accent(),true);
    opening.setVisibility(View.GONE);
    boardCard.addView(opening);
    studioBoard=new StudioBoard(c);
    studioBoard.setVisibility(View.GONE);
    boardCard.addView(studioBoard);
    preview=new ImageView(c);
    preview.setScaleType(ImageView.ScaleType.FIT_CENTER);
    preview.setContentDescription("Last recognized board");
    preview.setVisibility(View.GONE);
    boardCard.addView(preview,new LinearLayout.LayoutParams(-1,ui.dp(280)));
    col.addView(boardCard);
    ui.gap(col,12);

    start=ui.button("Start screen analysis",true,a::start);
    col.addView(start,new LinearLayout.LayoutParams(-1,ui.dp(50)));
    ui.gap(col,8);
    LinearLayout actionsRow=new LinearLayout(c);
    navButton(actionsRow,"Scan now",a::scan);
    hide=ui.button("Switch app",false,a::hide);
    hide.setContentDescription("Open another app");
    addAction(actionsRow,hide,1.15f);
    stop=ui.button("Stop",false,a::stop);
    addAction(actionsRow,stop,.75f);
    col.addView(actionsRow);
    ui.gap(col,16);

    LinearLayout analysis=ui.card();
    analysis.addView(ui.text("Analysis",22,MobileUi.FG,true));
    ui.gap(analysis,6);
    engine=ui.text("",15,MobileUi.MUTED,false);
    analysis.addView(engine);
    ui.gap(analysis,14);
    moves=ui.text("Waiting for a board",21,MobileUi.FG,true);
    analysis.addView(moves);
    ui.gap(analysis,10);
    eval=ui.text("Evaluation appears after a clean read",15,MobileUi.MUTED,false);
    analysis.addView(eval);
    ui.gap(analysis,10);
    bar=new ProgressBar(c,null,android.R.attr.progressBarStyleHorizontal);
    bar.setMax(1000);
    bar.setProgress(500);
    bar.setProgressTintList(android.content.res.ColorStateList.valueOf(ui.accent()));
    bar.setProgressBackgroundTintList(android.content.res.ColorStateList.valueOf(MobileUi.BORDER));
    bar.setContentDescription("Evaluation from White's perspective");
    analysis.addView(bar,new LinearLayout.LayoutParams(-1,ui.dp(8)));
    ui.gap(analysis,12);
    timing=ui.button(a.timeLabel(),false,a::timeSettings);
    timing.setContentDescription("Change thinking times");
    analysis.addView(timing);
    col.addView(analysis);
    ui.gap(col,14);

    LinearLayout floating=ui.card();
    floating.addView(ui.text("Floating menu",18,MobileUi.FG,true));
    ui.gap(floating,8);
    LinearLayout menuRow=new LinearLayout(c);
    Button openFloating=ui.button("Open menu",false,a::openFloatingMenu);
    openFloating.setContentDescription("Open floating menu");
    addAction(menuRow,openFloating,1);
    closeFloating=ui.button("Close menu",false,a::closeFloatingMenu);
    closeFloating.setContentDescription("Close floating menu");
    addAction(menuRow,closeFloating,1);
    floating.addView(menuRow);
    col.addView(floating);
  }
  private void addAction(LinearLayout row,Button button,float weight){
    LinearLayout.LayoutParams params=new LinearLayout.LayoutParams(0,-2,weight);
    if(row.getChildCount()>0)params.leftMargin=ui.dp(6);
    button.setPadding(ui.dp(6),0,ui.dp(6),0);
    row.addView(button,params);
  }
  private void navButton(LinearLayout row,String label,Runnable action){
    addAction(row,ui.button(label,false,action),1);
  }
  void setPosition(ChessPosition position,boolean bottom,String name){
    opening.setText(name);
    opening.setVisibility(name.isBlank()?View.GONE:View.VISIBLE);
    if(studioBoard.getParent()!=null){
      studioBoard.setVisibility(position==null?View.GONE:View.VISIBLE);
      studioBoard.position(position,bottom);
    }
  }
  void render(boolean running,String state,String recommendation,String evaluation,float whiteShare,Bitmap board){
    downloads.setVisibility(actions.downloadLabel().isEmpty()?View.GONE:View.VISIBLE);downloads.setText(actions.downloadLabel());timing.setText(actions.timeLabel());status.setText(state);moves.setText(recommendation);eval.setText(evaluation);bar.setVisibility(actions.option("evaluation_enabled",true)?View.VISIBLE:View.GONE);if(bar.getProgress()!=Math.round(whiteShare*1000)){
      if(android.os.Build.VERSION.SDK_INT>=24)bar.setProgress(Math.round(whiteShare*1000),true);
      else bar.setProgress(Math.round(whiteShare*1000));
    }start.setText(running?"Analysis is running":"Start screen analysis");start.setEnabled(!running);start.setAlpha(running?.55f:1f);stop.setEnabled(running);hide.setEnabled(running);hide.setAlpha(running?1f:.45f);
    closeFloating.setEnabled(actions.option(FloatingControls.ENABLED, true));
    closeFloating.setAlpha(closeFloating.isEnabled() ? 1f : .45f);
    preview.setVisibility(board==null||studioBoard.getVisibility()==View.VISIBLE?View.GONE:View.VISIBLE);if(board!=null)preview.setImageBitmap(board);
  }
}
