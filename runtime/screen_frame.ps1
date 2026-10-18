param([long]$Hwnd,[uint32]$ExpectedPid,[int]$X,[int]$Y,[int]$Width,[int]$Height,[string]$Output,[string]$Reference,[ValidateSet('custom_selection','room_keypad')][string]$Layout='custom_selection')
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
Add-Type -AssemblyName System.Drawing
Add-Type @'
using System; using System.Runtime.InteropServices;
public static class GameFrameNative {
 [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X,Y; public POINT(int x,int y){X=x;Y=y;} }
 [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
 [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h,out uint p);
 [DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(POINT p);
 [DllImport("user32.dll")] public static extern IntPtr GetAncestor(IntPtr h,uint f);
 [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
}
'@
[void][GameFrameNative]::SetProcessDPIAware()
function Check-Target {
 [uint32]$actual=0
 [void][GameFrameNative]::GetWindowThreadProcessId([IntPtr]$Hwnd,[ref]$actual)
 if ($actual -ne $ExpectedPid -or [GameFrameNative]::GetForegroundWindow().ToInt64() -ne $Hwnd) { throw 'foreground_game_changed' }
 foreach ($p in @(@(5,5),@(($Width-6),5),@(5,($Height-6)),@(($Width-6),($Height-6)),@([int]($Width/2),[int]($Height/2)))) {
  $point=[GameFrameNative+POINT]::new(($X+$p[0]),($Y+$p[1]))
  if ([GameFrameNative]::GetAncestor([GameFrameNative]::WindowFromPoint($point),2).ToInt64() -ne $Hwnd) { throw 'game_client_obscured' }
 }
}
if ($Width -ne 1450 -or $Height -ne 869) { throw 'unsupported_geometry' }
if (Test-Path -LiteralPath $Output) { throw 'capture_exists' }
Check-Target
$bitmap=[Drawing.Bitmap]::new($Width,$Height)
$referenceBitmap=[Drawing.Bitmap]::new($Reference)
$graphics=[Drawing.Graphics]::FromImage($bitmap)
try {
 $graphics.CopyFromScreen([Drawing.Point]::new($X,$Y),[Drawing.Point]::Empty,[Drawing.Size]::new($Width,$Height))
 $captured=[DateTime]::UtcNow.ToString('o')
 Check-Target
 $bitmap.Save($Output,[Drawing.Imaging.ImageFormat]::Png)
 $regions=@(@('custom_tab',286,243,105,43),@('custom_tile',96,505,139,32),@('confirm',1184,772,229,52))
 if ($Layout -eq 'room_keypad') {
  $regions=@(@('room_title',1110,148,87,33),@('custom_tab',286,243,105,43))
  $keys=@(@('1',1149,411),@('2',1255,411),@('3',1362,411),@('4',1149,500),@('5',1255,500),@('6',1362,500),@('7',1149,589),@('8',1255,589),@('9',1362,589),@('0',1149,682))
  foreach($key in $keys){$regions+=,@(('digit_'+$key[0]),($key[1]-16),($key[2]-21),32,42)}
 }
 $matches=@()
 foreach ($region in $regions) {
  $cx=[int]$region[1];$cy=[int]$region[2];$rw=[int]$region[3];$rh=[int]$region[4]
  $intersection=0;$expected=0;$actual=0
  for($dy=0;$dy -lt $rh;$dy++) { for($dx=0;$dx -lt $rw;$dx++) {
   $a=$referenceBitmap.GetPixel(($cx+$dx),($cy+$dy));$b=$bitmap.GetPixel(($cx+$dx),($cy+$dy))
   $wa=($a.R -ge 210 -and $a.G -ge 210 -and $a.B -ge 210)
   $wb=($b.R -ge 210 -and $b.G -ge 210 -and $b.B -ge 210)
   if($wa){$expected++};if($wb){$actual++};if($wa -and $wb){$intersection++}
  }}
  $score=if(($actual+$expected) -gt 0){2.0*$intersection/($actual+$expected)}else{0.0}
  $matches+=@{name=$region[0];score=$score;positive_pixels=$expected;center=@(($cx+[int]($rw/2)),($cy+[int]($rh/2)))}
 }
 $slots=@()
 if ($Layout -eq 'room_keypad') {
  foreach($slotX in @(1114,1191,1268,1344)) {
   $white=0
   for($sy=285;$sy -lt 338;$sy++){for($sx=$slotX;$sx -lt ($slotX+55);$sx++){
    $pixel=$bitmap.GetPixel($sx,$sy)
    if($pixel.R -ge 210 -and $pixel.G -ge 210 -and $pixel.B -ge 210){$white++}
   }}
   $slots+=@{white_pixels=$white;occupied=($white -ge 20)}
  }
 }
 @{status='captured';image=$Output;captured_at=$captured;matches=$matches;layout=$Layout;room_slots=$slots} | ConvertTo-Json -Depth 5 -Compress
} finally {$graphics.Dispose();$bitmap.Dispose();$referenceBitmap.Dispose()}
