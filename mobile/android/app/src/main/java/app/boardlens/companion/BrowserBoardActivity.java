package app.boardlens.companion;

import android.app.Activity;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.webkit.*;
import android.widget.LinearLayout;
import android.widget.TextView;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicLong;
import org.json.*;

/** Browser Reader in a dedicated phone WebView. It never grants pages access to native methods. */
public final class BrowserBoardActivity extends Activity {
    private final Handler main=new Handler(Looper.getMainLooper());
    private final LatestWorkQueue movesWorker=new LatestWorkQueue("Browser-moves");
    private final LatestWorkQueue evalWorker=new LatestWorkQueue("Browser-evaluation");
    private final ArrowEngines extraEngines=new ArrowEngines();
    private final LocalEngines moves=new LocalEngines(), evaluator=new LocalEngines();
    private final AtomicLong generation=new AtomicLong();
    private WebView page;
    private TextView status;
    private PhoneSettings settings;
    private boolean running,loaded;
    private int navigation;
    private String script,lastKey="",visibleFen="";
    private boolean whiteBottom=true;
    private ChessPosition position;
    private PhoneEngine.Result recommendation;
    private LocalEngines.Evaluated evaluation;
    private final SharedPreferences.OnSharedPreferenceChangeListener arrowSettings = (prefs, key) -> {
        if (ArrowEngines.isColorKey(key)) publish();
        else if (ArrowEngines.PREF.equals(key) && running && position != null) {
            extraEngines.request(this, position, settings.snapshot(), main, this::publish);
            publish();
        }
    };

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        settings=new PhoneSettings(this);
        try {
            script=readAsset("browser/content.js");
            script="(function(chrome){"+script+"})(window.BoardLensLocalChrome);";
            script="window.BoardLensLocalChrome={storage:{local:{get:(k,f)=>{let v={};try{v[k]=JSON.parse(localStorage.getItem('boardlens-'+k))}catch{}f(v)},set:o=>{for(const k in o)localStorage.setItem('boardlens-'+k,JSON.stringify(o[k]))}}},runtime:{sendMessage:async m=>{window.boardLensLocalPosition=m.boards[0]||null;return {'local:0':window.boardLensLocalHints||{fen:'',arrows:[]}}}}};"+script+readAsset("browser/reader.js");
        } catch(Exception error) {
            finish();
            return;
        }
        MobileUi ui=new MobileUi(this);
        LinearLayout root=ui.column(), controls=new LinearLayout(this);
        controls.addView(ui.button("‹ Back",false,this::finish));
        controls.addView(ui.button("Chess.com",false,()->page.loadUrl("https://www.chess.com/play/computer")));
        controls.addView(ui.button("Lichess",false,()->page.loadUrl("https://lichess.org/analysis")));
        root.addView(controls);
        LinearLayout summary=ui.column();
        summary.addView(ui.button("Arrow engines",false,()->ArrowEngineMenu.edit(this,settings)),
            new LinearLayout.LayoutParams(-1,ui.dp(48)));
        root.addView(summary);
        status=ui.text("Open a board",14,MobileUi.MUTED,false);
        status.setPadding(ui.dp(10),ui.dp(4),ui.dp(10),ui.dp(4));
        root.addView(status);
        page=new WebView(this);
        page.setBackgroundColor(Color.rgb(29,33,31));
        page.getSettings().setJavaScriptEnabled(true);
        page.getSettings().setDomStorageEnabled(true);
        page.getSettings().setAllowFileAccess(false);
        page.getSettings().setAllowContentAccess(false);
        page.getSettings().setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        page.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                return request.isForMainFrame() && !chessHost(request.getUrl());
            }
            @Override public void onPageStarted(WebView view,String url,android.graphics.Bitmap icon) {
                navigation++;
                loaded=false;
                reset();
            }
            @Override public void onPageFinished(WebView view,String url) {
                if(!chessHost(Uri.parse(url)))return;
                view.evaluateJavascript("if(!window.boardLensLocalLoaded){window.boardLensLocalLoaded=true;"+script+"}",null);
                loaded=true;
            }
        });
        root.addView(page,new LinearLayout.LayoutParams(-1,0,1));
        MobileUi.inset(this,root);
        setContentView(root);
        page.loadUrl("https://lichess.org/analysis");
    }

    static boolean chessHost(Uri uri) {
        String host=uri.getHost();
        return "https".equals(uri.getScheme()) &&
               ("www.chess.com".equals(host)||"lichess.org".equals(host)) &&
               (uri.getPort()==-1||uri.getPort()==443);
    }

    private String readAsset(String path)throws Exception {
        try(var stream=getAssets().open(path)){
            return new String(Streams.read(stream,100_000),StandardCharsets.UTF_8);
        }
    }

    private final Runnable scan=new Runnable() {
        public void run(){
            if(!running)return;
            if(loaded && page.getUrl()!=null && chessHost(Uri.parse(page.getUrl()))){
                int pageToken=navigation;
                page.evaluateJavascript("JSON.stringify(window.boardLensLocalPosition??null)",raw->{
                    if(!running||!loaded||pageToken!=navigation||raw==null||raw.length()>4096)return;
                    try {
                        Object value=new JSONTokener(raw).nextValue();
                        if(value instanceof String s && !s.equals("null"))observe(new JSONObject(s));
                        else if(!lastKey.isEmpty()){reset();status.setText("Waiting for a visible chessboard");}
                    } catch (JSONException|IllegalArgumentException ignored) {}
                });
            }
            main.postDelayed(this,85);
        }
    };

    private void observe(JSONObject read)throws JSONException {
        String fen=read.getString("fen");
        if(fen.length()>160)return;
        boolean bottom=read.getBoolean("white_bottom");
        String key=fen+":"+bottom+":"+read.optString("game_result","");
        if(key.equals(lastKey))return;
        lastKey=key;
        visibleFen=fen;
        whiteBottom=bottom;
        String result=GameEndText.reason(read.optString("game_result",""));
        if(result!=null){reset();status.setText("Game over · "+result);return;}
        ChessPosition board=new ChessPosition(fen);
        if(!read.optBoolean("exact")){
            String turn=read.isNull("turn_hint")?"Auto":read.optBoolean("turn_hint")?"White":"Black";
            String placement=board.placement();
            board=position==null?null:ChessPosition.sync(position,placement,"Auto",false);
            if(board==null && position==null)board=ChessPosition.sync(new ChessPosition(ChessPosition.START_FEN),placement,"Auto",false);
            if(board==null || !turn.equals("Auto") && board.white!=turn.equals("White"))
                board=ChessPosition.sync(null,placement,turn,true);
        }
        if(board==null||!board.valid()||board.legal().isEmpty()){
            reset();status.setText("No legal move on this board");return;
        }
        position=board;
        recommendation=null;
        long token=generation.incrementAndGet();
        moves.cancel();evaluator.cancel();
        ChessPosition root=board;
        PhoneSettings configuration=settings.snapshot();
        status.setText((board.white?"White":"Black")+" to move");
        publish();
        extraEngines.request(this,root,configuration,main,this::publish);
        if(EngineCatalog.ready(this,configuration.engine())){
            movesWorker.submit(()->{
                try {
                    var resultLines=moves.recommend(this,root,configuration,()->token==generation.get(),
                        (r,done)->{if(done||configuration.early())main.post(()->{if(token==generation.get()){recommendation=r;publish();}});});
                    main.post(()->{
                        if(token!=generation.get())return;
                        recommendation=resultLines;
                        publish();
                    });
                }catch(Exception error){main.post(()->{if(token==generation.get())status.setText("Engine: "+error.getMessage());});}
            });
        }else status.setText("Install "+EngineCatalog.get(configuration.engine()).name()+" in Phone screen → Models");
        if(configuration.evaluationEnabled()&&EngineCatalog.ready(this,configuration.evaluator())){
            evalWorker.submit(()->{
                try {
                    var score=evaluator.evaluate(this,root,configuration,r->acceptScore(token,r));
                    acceptScore(token,score);
                }catch(Exception ignored){}
            });
        }
    }

    private void acceptScore(long token,LocalEngines.Evaluated score) {
        main.post(()->{if(token==generation.get()){evaluation=score;publish();}});
    }

    private void publish() {
        if(!loaded||position==null)return;
        try {
            JSONArray arrows=new JSONArray();
            if(settings.arrows() && recommendation!=null && (!settings.onlyMine()||position.white==whiteBottom)){
                int rank=0;
                for(var line:recommendation.lines()){
                    arrows.put(new JSONObject().put("move",line.move()).put("color",rank++==0?settings.mainColor():"#ba9cff"));
                }
                var mainLine=recommendation.lines().isEmpty()?null:recommendation.lines().get(0);
                if(mainLine!=null&&!settings.onlyMine()&&settings.predict()&&mainLine.pv().size()>1)
                    arrows.put(new JSONObject().put("move",mainLine.pv().get(1)).put("color","#51d9da").put("dashed",true));
            }
            if(settings.arrows()&&(!settings.onlyMine()||position.white==whiteBottom)){
                for(var move:extraEngines.arrows(settings))arrows.put(new JSONObject().put("move",move.move())
                    .put("color",String.format(Locale.ROOT,"#%06x",move.color()&0xffffff)).put("engine",move.engine()));
            }
            JSONObject data=new JSONObject().put("fen",visibleFen).put("arrows",arrows);
            if(settings.evaluationEnabled()){
                JSONObject score=new JSONObject().put("provider",EngineCatalog.get(settings.evaluator()).name());
                if(evaluation!=null)score.put("white_share",evaluation.whiteShare()).put("score",evaluation.badge());
                data.put("evaluation",score);
            }else data.put("evaluation",JSONObject.NULL);
            page.evaluateJavascript("window.boardLensLocalHints="+data.toString(),null);
        }catch(JSONException ignored){}
    }

    private void reset() {
        generation.incrementAndGet();moves.cancel();evaluator.cancel();extraEngines.cancel();
        position=null;recommendation=null;evaluation=null;lastKey="";
        if(loaded&&page!=null)page.evaluateJavascript("window.boardLensLocalHints=null",null);
    }
    @Override protected void onStart(){super.onStart();PhoneUiVisibility.start(this);running=true;settings.p.registerOnSharedPreferenceChangeListener(arrowSettings);main.post(scan);}
    @Override protected void onStop(){running=false;settings.p.unregisterOnSharedPreferenceChangeListener(arrowSettings);main.removeCallbacks(scan);reset();PhoneUiVisibility.stop(this);super.onStop();}
    @Override protected void onDestroy(){
        extraEngines.close();
        movesWorker.close(moves::close);evalWorker.close(evaluator::close);
        if(page!=null)page.destroy();
        super.onDestroy();
    }
}
