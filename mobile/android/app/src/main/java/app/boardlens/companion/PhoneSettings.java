package app.boardlens.companion;

import android.content.Context;
import android.content.SharedPreferences;

/** Deliberately separate from computer companion preferences. */
final class PhoneSettings {
  private static final String[] RANK_COLORS = {"#ffc65c", "#61b9ff", "#c49bff", "#ff90b2", "#83e4bb"};
  final SharedPreferences p;

  String arrowColor(int rank) {
    return rank == 0 ? mainColor() : RANK_COLORS[rank % RANK_COLORS.length];
  }

  private java.util.Map<String,?> frozen;
  PhoneSettings snapshot(){PhoneSettings copy=new PhoneSettings(p);copy.frozen=new java.util.HashMap<>(p.getAll());return copy;}
  PhoneSettings override(java.util.Map<String,?> values){
    PhoneSettings copy=new PhoneSettings(p);java.util.Map<String,Object> map=new java.util.HashMap<>(frozen==null?p.getAll():frozen);
    map.putAll(values);copy.frozen=map;return copy;
  }
  PhoneSettings continuation(float secondsLeft){
    return override(java.util.Map.of("seconds",Math.min(seconds(),secondsLeft),"mode",mode().equals("Depth")?"Time + depth":mode(),"moves",1));
  }
  private PhoneSettings(SharedPreferences prefs){p=prefs;}
  private float getFloat(String key,float value){return frozen==null?p.getFloat(key,value):(frozen.containsKey(key)?((Number)frozen.get(key)).floatValue():value);}
  private int getInt(String key,int value){return frozen==null?p.getInt(key,value):(frozen.containsKey(key)?((Number)frozen.get(key)).intValue():value);}
  private boolean getBoolean(String key,boolean value){return frozen==null?p.getBoolean(key,value):(frozen.containsKey(key)?(Boolean)frozen.get(key):value);}
  private String getString(String key,String value){return frozen==null?p.getString(key,value):(frozen.containsKey(key)?(String)frozen.get(key):value);}

  PhoneSettings(Context c) {
    this(c,"phone-screen");
  }

  PhoneSettings(Context c,String name){p=c.getSharedPreferences(name,0);}

  float seconds() {
    return getFloat("seconds", .5f);
  }

  float evaluationSeconds(){return Math.max(.03f,Math.min(30f,getFloat("evaluation_seconds",.2f)));}
  int evaluationDepth(){return Math.max(1,Math.min(40,getInt("evaluation_depth",18)));}
  boolean evaluationEnabled(){return getBoolean("evaluation_enabled",true);}
  boolean screenEvaluation(){return getBoolean("screen_evaluation",true);}
  String evaluationPosition(){return getString("evaluation_position","Auto");}

  float evaluationX(){return Math.max(0,Math.min(1,getFloat("evaluation_x",.5f)));}
  float evaluationY(){return Math.max(0,Math.min(1,getFloat("evaluation_y",.1f)));}
  boolean evaluationVertical(){return getBoolean("evaluation_vertical",false);}

  int depth() {
    return getInt("depth", 18);
  }

  int moves() {
    return getInt("moves", 1);
  }

  int threads() {
    return getInt("threads", 1);
  }

  int skill() {
    return getInt("skill", 20);
  }

  String mainColor() {
    String value=getString(ArrowEngines.MAIN_COLOR,"#ffc65c");
    return value.matches("#[0-9a-fA-F]{6}")?value:"#ffc65c";
  }

  String style(){return getString("style","Balanced");}

  boolean arrows() {
    return getBoolean("arrows", true);
  }

  boolean steady() {
    return getBoolean("steady", true);
  }

  boolean lockMove(){ return getBoolean("lock_move",false); }

  boolean predict() {
    return getBoolean("predict", true);
  }

  static final int MAX_LOOKAHEAD_PLIES = 32;
  int predictionPlies() { return Math.max(1, Math.min(MAX_LOOKAHEAD_PLIES, getInt("prediction_plies", 3))); }

  float predictionSeconds() { return getFloat("prediction_seconds", 3f); }

  boolean early() { return getBoolean("early", true); }

  boolean onlyMine() {
    return getBoolean("onlyMine", false);
  }

  String orientation() {
    return getString("orientation", "Auto");
  }

  String turn() {
    return getString("turn", "Auto");
  }

  String mode() {
    return getString("mode", "Time + depth");
  }

  int rating() { return getInt("rating",1500); }

  String backend() { return "On phone"; }

  String engine() {
    return getString("engine", "stockfish");
  }

  String evaluator() {
    return getString("evaluator", "stockfish");
  }
}
