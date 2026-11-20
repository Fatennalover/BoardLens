using Android.Runtime;
using Java.Interop;
namespace BoardLens.Mobile;
[Register("app/boardlens/companion/TinyRuntime")]
[Preserve(AllMembers=true)]
public class TinyRuntime:Java.Lang.Object {
 private readonly TinyCore engine=new();
 [Export] public TinyRuntime(){}
 [Export("search")] public string Search(int id,string fen,int milliseconds) { try { return engine.Search(id,fen,milliseconds); } catch(Exception error) { return System.Text.Json.JsonSerializer.Serialize(new { error=error.GetBaseException().Message, cancelled=error is OperationCanceledException }); } }
 [Export("cancel")] public void Cancel()=>engine.Cancel();
 [Export("release")] public void Release()=>engine.Release();
}
