package app.boardlens.companion;

import android.app.Activity;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.Message;
import android.webkit.*;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;
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
    private WebView popup;
    private Uri site=Uri.parse("https://lichess.org/analysis");
    private TextView status;
    private PhoneSettings settings;
    private FloatingControls floating;
    private boolean running,loaded,analysisEnabled=true;
    private int navigation;
    private String script,lastKey="",visibleFen="";
    private boolean whiteBottom=true;
    private ChessPosition position;
    private MoveAdvantageDialog moveAdvantage;
    private CoachPanel coach;
    private PhoneEngine.Result recommendation;
    private LocalEngines.Evaluated evaluation;
    private final Runnable observeSettings = () -> lastKey="";
    private final SharedPreferences.OnSharedPreferenceChangeListener preferenceListener = (prefs, key) -> {
        if (FloatingControls.BROWSER_ENABLED.equals(key)) return;
        if (CoachPanel.PREFERENCE.equals(key)) {
            renderCoach();
            if (coach.count()>0) lastKey="";
            return;
        }
        if (ArrowEngines.isColorKey(key) || "arrows".equals(key) || "onlyMine".equals(key)
                || "screen_evaluation".equals(key)) publish();
        else if (ArrowEngines.PREF.equals(key) && running && analysisEnabled && position != null) {
            extraEngines.request(this, position, settings.snapshot(), main, this::publish);
            publish();
        } else if (running && analysisEnabled) {
            if ("evaluation_enabled".equals(key)) publish();
            if ("predict".equals(key) || "prediction_plies".equals(key)) showPrediction(recommendation);
            main.removeCallbacks(observeSettings);
            main.postDelayed(observeSettings, 80);
        }
    };

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        if (state != null) analysisEnabled=state.getBoolean("analysis_enabled",true);
        settings=new PhoneSettings(this);
        try {
            script=readAsset("browser/content.js");
            script="(function(chrome){"+script+"})(window.BoardLensLocalChrome);";
            script="window.BoardLensLocalChrome={storage:{local:{get:(k,f)=>{let v={};try{v[k]=JSON.parse(localStorage.getItem('boardlens-'+k))}catch{}f(v)},set:o=>{for(const k in o)localStorage.setItem('boardlens-'+k,JSON.stringify(o[k]))}}},runtime:{sendMessage:async m=>{window.boardLensLocalPosition=m.boards[0]||null;const hint=window.boardLensLocalHints;return {evaluation_visible:!!hint?.evaluation,'local:0':hint||{fen:'',arrows:[]}}}}};"+script+readAsset("browser/reader.js");
        } catch(Exception error) {
            finish();
            return;
        }
        MobileUi ui=new MobileUi(this);
        LinearLayout root=ui.column(), controls=new LinearLayout(this);
        addToolbarButton(controls,ui.button("‹ Back",false,this::finish));
        addToolbarButton(controls,ui.button("Chess.com",false,()->openSite("https://www.chess.com/play/computer")));
        addToolbarButton(controls,ui.button("Lichess",false,()->openSite("https://lichess.org/analysis")));
        Button menu=ui.button("Menu",false,()->floating.toggle());
        menu.setContentDescription("Floating menu");
        addToolbarButton(controls,menu);
        root.addView(controls);
        status=ui.text("Direct read · Open a board",14,MobileUi.MUTED,false);
        status.setPadding(ui.dp(10),ui.dp(4),ui.dp(10),ui.dp(4));
        LinearLayout boardStatus=new LinearLayout(this);
        boardStatus.setGravity(android.view.Gravity.CENTER_VERTICAL);
        boardStatus.addView(status,new LinearLayout.LayoutParams(0,-2,1));
        coach=new CoachPanel(this,ui,settings);
        boardStatus.addView(ui.button("Coach",false,()->coach.options(this::renderCoach)));
        boardStatus.addView(ui.button("Move advantage",false,()->{
            if(moveAdvantage==null)moveAdvantage=new MoveAdvantageDialog(this);
            moveAdvantage.show(position);
        }));
        root.addView(boardStatus);
        root.addView(coach.view(),new LinearLayout.LayoutParams(-1,ui.dp(150)));
        renderCoach();
        page=new WebView(this);
        page.setBackgroundColor(Color.rgb(29,33,31));
        page.getSettings().setJavaScriptEnabled(true);
        page.getSettings().setDomStorageEnabled(true);
        page.getSettings().setAllowFileAccess(false);
        page.getSettings().setAllowContentAccess(false);
        page.getSettings().setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        page.getSettings().setSupportMultipleWindows(true);
        page.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                if (!request.isForMainFrame()) return false;
                Uri destination=request.getUrl();
                if (isGoogleSignIn(destination)) {
                    showGoogleSignInMessage();
                    return true;
                }
                return !chessHost(destination);
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
        page.setWebChromeClient(new WebChromeClient() {
            @Override public boolean onCreateWindow(WebView view,boolean dialog,boolean userGesture,Message result) {
                if (!userGesture || view.getUrl()==null || !chessHost(Uri.parse(view.getUrl()))) return false;
                connectPopup(result);
                return true;
            }
        });
        FrameLayout viewport=new FrameLayout(this);
        viewport.addView(page,new FrameLayout.LayoutParams(-1,-1));
        floating=new FloatingControls(this,settings,new FloatingControls.Actions() {
            public void scan() {
                analysisEnabled=true;
                reset();
                status.setText("Reading the visible board…");
            }
            public void stop() {
                analysisEnabled=false;
                reset();
                status.setText("Analysis paused · use Scan now to resume");
            }
            public void geometryChanged() {}
        },viewport);
        viewport.addOnLayoutChangeListener((view,left,top,right,bottom,oldLeft,oldTop,oldRight,oldBottom)->{
            // Attach after layout so the initial bubble receives its own layout pass.
            if (right-left!=oldRight-oldLeft || bottom-top!=oldBottom-oldTop)
                viewport.post(floating::displayChanged);
        });
        root.addView(viewport,new LinearLayout.LayoutParams(-1,0,1));
        MobileUi.inset(this,root);
        setContentView(root);
        if (state!=null) {
            Uri restored=Uri.parse(state.getString("browser_site",""));
            if (chessHost(restored)) site=restored;
        }
        if (state==null || page.restoreState(state)==null) page.loadUrl(site.toString());
    }

    private void openSite(String address) {
        site=Uri.parse(address);
        page.loadUrl(address);
    }

    private static void addToolbarButton(LinearLayout row, Button button) {
        button.setPadding(0,button.getPaddingTop(),0,button.getPaddingBottom());
        row.addView(button,new LinearLayout.LayoutParams(0,-2,1));
    }

    static boolean chessHost(Uri uri) {
        String host=uri==null?null:uri.getHost();
        return secureWeb(uri) &&
               ("www.chess.com".equals(host)||"lichess.org".equals(host));
    }

    private static boolean secureWeb(Uri uri) {
        return uri!=null && "https".equals(uri.getScheme()) && (uri.getPort()==-1||uri.getPort()==443)
            && uri.getUserInfo()==null;
    }

    static boolean isGoogleSignIn(Uri uri) {
        if (!secureWeb(uri)) return false;
        if ("accounts.google.com".equals(uri.getHost())) return true;
        if (!chessHost(uri) || uri.getPath()==null) return false;
        return uri.getPath().toLowerCase(Locale.ROOT).matches("/(?:login|auth|oauth)(?:/[^/]+)*/google/?");
    }

    static Uri browserLogin(Uri site) {
        if (!chessHost(site)) return null;
        return Uri.parse("https://"+site.getHost()+"/login");
    }

    private void showGoogleSignInMessage() {
        Toast.makeText(this,"Use your chess site username and password in Browser Reader.",Toast.LENGTH_LONG).show();
    }

    private void connectPopup(Message result) {
        discardPopup();
        WebView bridge=new WebView(this);
        popup=bridge;
        bridge.getSettings().setBlockNetworkLoads(true);
        bridge.getSettings().setAllowFileAccess(false);
        bridge.getSettings().setAllowContentAccess(false);
        bridge.setWebViewClient(new WebViewClient() {
            private void route(Uri destination) {
                if ("about:blank".equals(destination.toString()) || popup!=bridge) return;
                main.post(()->{
                    if (popup!=bridge) return;
                    discardPopup();
                    if (!running) return;
                    if (isGoogleSignIn(destination)) showGoogleSignInMessage();
                    else if (chessHost(destination) && "/login".equals(destination.getPath()))
                        page.loadUrl(browserLogin(destination).toString());
                });
            }
            @Override public boolean shouldOverrideUrlLoading(WebView view,WebResourceRequest request) {
                if (request.isForMainFrame()) route(request.getUrl());
                return true;
            }
            @Override public void onPageStarted(WebView view,String url,android.graphics.Bitmap icon) {
                route(Uri.parse(url));
            }
        });
        ((WebView.WebViewTransport)result.obj).setWebView(bridge);
        result.sendToTarget();
        main.postDelayed(()->{if (popup==bridge) discardPopup();},5000);
    }

    private void discardPopup() {
        if (popup==null) return;
        WebView previous=popup;
        popup=null;
        previous.destroy();
    }

    private String readAsset(String path)throws Exception {
        try(var stream=getAssets().open(path)){
            return new String(Streams.read(stream,100_000),StandardCharsets.UTF_8);
        }
    }

    private final Runnable scan=new Runnable() {
        public void run(){
            if(!running)return;
            if(analysisEnabled && loaded && page.getUrl()!=null && chessHost(Uri.parse(page.getUrl()))){
                int pageToken=navigation;
                page.evaluateJavascript("JSON.stringify(window.boardLensLocalPosition??null)",raw->{
                    if(!running||!analysisEnabled||!loaded||pageToken!=navigation||raw==null||raw.length()>4096)return;
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
        if(position==null||!position.fen().equals(board.fen()))evaluation=null;
        position=board;
        if(moveAdvantage!=null)moveAdvantage.update(board);
        recommendation=null;
        long token=generation.incrementAndGet();
        moves.cancel();evaluator.cancel();
        ChessPosition root=board;
        PhoneSettings configuration=coach.withCandidates(settings.snapshot());
        status.setText(turnText(board));
        publish();
        extraEngines.request(this,root,configuration,main,this::publish);
        if(EngineCatalog.ready(this,configuration.engine())){
            movesWorker.submit(()->{
                try {
                    var resultLines=moves.recommend(this,root,configuration,()->token==generation.get(),
                        (r,done)->{if(done||configuration.early())main.post(()->acceptRecommendation(token,r));});
                    main.post(()->acceptRecommendation(token,resultLines));
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

    private void acceptRecommendation(long token,PhoneEngine.Result result) {
        if(token!=generation.get())return;
        recommendation=result;
        showPrediction(result);
        publish();
    }

    private static String turnText(ChessPosition board) {
        return "Direct read · "+(board.white?"White":"Black")+" to move";
    }

    private void showPrediction(PhoneEngine.Result result) {
        if(position==null)return;
        String text=turnText(position);
        if(settings.predict()&&settings.predictionPlies()>1&&result!=null&&!result.lines().isEmpty()){
            var first=result.lines().get(0);
            if(first.pv().size()>1&&position.legal().contains(first.move())){
                ChessPosition next=position.play(first.move());
                String reply=first.pv().get(1);
                if(next.legal().contains(reply))text+=" · Predicted reply "+next.notation(reply);
            }
        }
        status.setText(text);
    }

    private void renderCoach() {
        coach.render(position, recommendation, settings.evaluationEnabled() ? evaluation : null,
                position != null && (!settings.onlyMine() || position.white == whiteBottom),
                position == null ? "Open a visible chessboard to get coaching." :
                "Waiting for engine suggestions.");
    }

    private void publish() {
        renderCoach();
        if(!analysisEnabled||!loaded||position==null)return;
        try {
            JSONArray arrows=new JSONArray();
            if(settings.arrows() && recommendation!=null && (!settings.onlyMine()||position.white==whiteBottom)){
                int rank=0;
                var lines=recommendation.lines();
                for(var line:lines.subList(0,Math.min(settings.moves(),lines.size()))){
                    arrows.put(new JSONObject().put("move",line.move()).put("color",rank++==0?settings.mainColor():"#ba9cff"));
                }
            }
            if(settings.arrows()&&(!settings.onlyMine()||position.white==whiteBottom)){
                for(var move:extraEngines.arrows(settings))arrows.put(new JSONObject().put("move",move.move())
                    .put("color",String.format(Locale.ROOT,"#%06x",move.color()&0xffffff)).put("engine",move.engine()));
            }
            JSONObject data=new JSONObject().put("fen",visibleFen).put("arrows",arrows);
            if(settings.evaluationEnabled()&&settings.screenEvaluation()){
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
        if(moveAdvantage!=null)moveAdvantage.update(null);
        if(coach!=null)renderCoach();
        if(loaded&&page!=null)page.evaluateJavascript("window.boardLensLocalHints=null",null);
    }
    @Override protected void onStart(){
        super.onStart();
        if (floating==null) return;
        PhoneUiVisibility.start(this);running=true;
        settings.p.registerOnSharedPreferenceChangeListener(preferenceListener);
        floating.show(true);main.post(scan);
    }
    @Override protected void onStop(){
        if (floating==null) { super.onStop(); return; }
        running=false;settings.p.unregisterOnSharedPreferenceChangeListener(preferenceListener);
        main.removeCallbacks(scan);main.removeCallbacks(observeSettings);floating.show(false);
        if (page!=null) CookieManager.getInstance().flush();
        discardPopup();reset();PhoneUiVisibility.stop(this);super.onStop();
    }
    @Override protected void onSaveInstanceState(Bundle state){
        super.onSaveInstanceState(state);
        state.putBoolean("analysis_enabled",analysisEnabled);
        state.putString("browser_site",site.toString());
        if (page!=null) page.saveState(state);
    }
    @Override protected void onDestroy(){
        if(moveAdvantage!=null)moveAdvantage.close();
        main.removeCallbacksAndMessages(null);
        discardPopup();
        extraEngines.close();
        movesWorker.close(moves::close);evalWorker.close(evaluator::close);
        if(page!=null)page.destroy();
        super.onDestroy();
    }
}
