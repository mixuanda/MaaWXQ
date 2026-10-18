param([long]$Hwnd,[uint32]$ExpectedPid,[int]$X,[int]$Y,[int]$Width,[int]$Height,[string]$Output,[string]$Reference,[ValidateSet('custom_selection','room_keypad','custom_lobby','custom_lobby_slot','custom_lobby_bot_menu','custom_lobby_onebot','custom_lobby_fill','custom_lobby_ready','custom_lobby_start','guidance_settings','room_options','room_options_close','encyclopedia','battle_controls','battle_settings','exit_confirmation','ended_battle','custom_results','main_hub','main_hub_modes','chess_collection','yixing_details','yixing_skill_tab','yixing_ability_tooltip','yixing_rules_secret','yixing_secret_reward','encyclopedia_back','yixing_details_back','chess_collection_back','empty_lobby_options','yixing_character_choice','yixing_character_confirm')][string]$Layout='custom_selection',[string]$MenuReference)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
Add-Type -AssemblyName System.Drawing
Add-Type -ReferencedAssemblies System.Drawing @'
using System; using System.Runtime.InteropServices;
public static class GameFrameNative {
 [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X,Y; public POINT(int x,int y){X=x;Y=y;} }
 [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
 [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h,out uint p);
 [DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(POINT p);
 [DllImport("user32.dll")] public static extern IntPtr GetAncestor(IntPtr h,uint f);
 [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
 // Bounded symmetric one-pixel comparison for translated, antialiased slot art.
 public static double SpatialScore(System.Drawing.Bitmap a,System.Drawing.Bitmap b,
     int ax,int ay,int bx,int by,int width,int height,bool rgb) {
  var ac=new System.Drawing.Color[width,height];var bc=new System.Drawing.Color[width,height];
  int amin=765,amax=0,bmin=765,bmax=0;
  for(int y=0;y<height;y++)for(int x=0;x<width;x++){
   ac[x,y]=a.GetPixel(ax+x,ay+y);bc[x,y]=b.GetPixel(bx+x,by+y);
   int av=ac[x,y].R+ac[x,y].G+ac[x,y].B,bv=bc[x,y].R+bc[x,y].G+bc[x,y].B;
   amin=Math.Min(amin,av);amax=Math.Max(amax,av);bmin=Math.Min(bmin,bv);bmax=Math.Max(bmax,bv);
  }
  if(!rgb&&(amax-amin<60||bmax-bmin<60))return 0;
  if(rgb){
   long error=0;
   for(int direction=0;direction<2;direction++){
    var first=direction==0?ac:bc;var second=direction==0?bc:ac;
    for(int y=0;y<height;y++)for(int x=0;x<width;x++){
     var value=first[x,y];int best=765;
     for(int dy=-1;dy<=1;dy++)for(int dx=-1;dx<=1;dx++){
      int sx=x+dx,sy=y+dy;if(sx<0||sy<0||sx>=width||sy>=height)continue;
      var candidate=second[sx,sy];
      best=Math.Min(best,Math.Abs(value.R-candidate.R)+Math.Abs(value.G-candidate.G)+Math.Abs(value.B-candidate.B));
     }
     error+=best;
    }
   }
   return 1.0-error/(2.0*width*height*765.0);
  }
  double at=(amin+amax)/2.0,bt=(bmin+bmax)/2.0;int total=0,matched=0;
  for(int direction=0;direction<2;direction++){
   var first=direction==0?ac:bc;var second=direction==0?bc:ac;
   double ft=direction==0?at:bt,st=direction==0?bt:at;
   for(int y=0;y<height;y++)for(int x=0;x<width;x++){
    var value=first[x,y];if(!rgb&&value.R+value.G+value.B<ft)continue;
    total++;bool found=false;
    for(int dy=-1;dy<=1&&!found;dy++)for(int dx=-1;dx<=1;dx++){
     int sx=x+dx,sy=y+dy;if(sx<0||sy<0||sx>=width||sy>=height)continue;
     var candidate=second[sx,sy];
     bool equal=rgb?(Math.Abs(value.R-candidate.R)<=12&&Math.Abs(value.G-candidate.G)<=12&&Math.Abs(value.B-candidate.B)<=12):candidate.R+candidate.G+candidate.B>=st;
     if(equal){found=true;break;}
    }
    if(found)matched++;
   }
  }
  return total==0?0:(double)matched/total;
 }
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
$menuBitmap=$null
if($Layout -eq 'custom_lobby_fill'){$menuBitmap=[Drawing.Bitmap]::new($MenuReference)}
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
 if ($Layout -in @('custom_lobby','custom_lobby_slot','custom_lobby_bot_menu','empty_lobby_options')) {
  $regions=@(@('lobby_title',633,11,188,30),@('ai_settings',220,805,72,30),@('start_game',1188,771,231,58))
  $index=0
  foreach($left in @(469,627,785,944,1102)){$index++;$regions+=,@(('empty_'+$index),$left,361,38,38,'rgb')}
  if($Layout -eq 'custom_lobby_slot'){$regions+=,@('empty_slot_menu',445,436,87,36,'rgb')}
  if($Layout -eq 'custom_lobby_bot_menu'){$regions+=,@('empty_slot_robot',445,473,87,32,'rgb')}
  if($Layout -eq 'empty_lobby_options'){$regions+=,@('room_settings',1389,24,37,38)}
 }
 if ($Layout -eq 'guidance_settings') {
  $regions=@(@('settings_back',20,22,28,35),@('settings_title',49,21,56,30),@('ai_master',231,78,112,30),@('lingbao_selected',82,515,43,23))
 }
 if ($Layout -eq 'custom_lobby_onebot') {
  $regions=@(@('lobby_title',633,11,188,30),@('room_settings',1389,24,37,38),@('bot_label_1',456,436,66,31),@('bot_avatar_1',451,342,74,74,'rgb'))
  $index=1
  foreach($left in @(627,785,944,1102)){$index++;$regions+=,@(('empty_'+$index),$left,361,38,38,'rgb')}
 }
 if ($Layout -eq 'custom_lobby_fill') {
  $regions=,@('lobby_title',633,11,188,30)
  $index=0
  foreach($centerX in @(488,646,805,963,1121)) {
   $index++
   $emptyReferenceX=if($index -eq 1){627}else{$centerX-19}
   $regions+=,@(('slot_'+$index+'_empty'),($centerX-19),361,38,38,'rgb',$emptyReferenceX,361)
   $regions+=,@(('slot_'+$index+'_bot_avatar'),($centerX-28),351,56,56,'rgb_spatial',460,351)
   $regions+=,@(('slot_'+$index+'_bot_label'),($centerX-32),436,66,31,'adaptive_spatial',456,436)
   $operationReferenceX=if($index -eq 1){603}else{$centerX-43}
   $regions+=,@(('slot_'+$index+'_operation'),($centerX-43),436,87,36,'adaptive',$operationReferenceX,436)
   $regions+=,@(('slot_'+$index+'_robot_menu'),($centerX-28),477,58,26,'adaptive_spatial',460,477,'menu')
  }
 }
 $settingsChoices=@()
 if ($Layout -eq 'yixing_character_choice') {
  $regions=@(@('selection_title',682,13,59,19,'adaptive_shift_x8'),@('yixing_name',428,831,40,24,'adaptive'),@('picker_context',182,831,36,24,'adaptive'),@('yixing_target',421,764,52,52,'rgb'))
 }
 if ($Layout -eq 'yixing_character_confirm') {
  $regions=@(@('selection_title',682,13,59,19,'adaptive_shift_x8'),@('selected_yixing',428,831,40,24,'adaptive'),@('confirm_label',1306,789,43,28,'dark_adaptive'))
 }
 if ($Layout -eq 'encyclopedia_back') {
  $regions=@(@('back',21,21,26,36,'adaptive'),@('encyclopedia_title',50,23,52,32,'adaptive'),@('tournament_tab',601,21,93,26,'adaptive'),@('chess_cards_tab',1110,85,67,30,'adaptive'))
 }
 if ($Layout -eq 'yixing_details_back') {
  $regions=@(@('back',21,21,26,36,'adaptive'),@('collection_title',48,23,54,31,'adaptive'),@('yixing_title',1156,78,49,29,'adaptive'),@('classic_skin',1208,78,93,29,'adaptive'),@('equipped',690,796,73,31,'adaptive'))
 }
 if ($Layout -eq 'chess_collection_back') {
  $regions=@(@('back',21,21,26,36,'adaptive'),@('collection_title',48,23,54,31,'adaptive'),@('players_tab',643,22,50,29,'adaptive'),@('strength_tab',757,22,50,29,'adaptive'),@('yixing_name',598,294,48,30,'adaptive'))
 }
 if ($Layout -eq 'yixing_secret_reward') {
  $regions=@(@('encyclopedia_title',50,23,52,32,'adaptive'),@('tournament_tab',601,21,93,26,'adaptive'),@('chess_cards_tab',1110,85,67,30,'adaptive'),@('yixing_row',71,440,34,22,'adaptive'),@('mission_name',1231,274,103,30,'adaptive'),@('mission_rounds',584,468,82,17,'adaptive'),@('reward_label',567,586,31,20,'adaptive'))
 }
 if ($Layout -eq 'yixing_rules_secret') {
  $regions=@(@('encyclopedia_title',50,23,52,32,'adaptive'),@('tournament_tab',601,21,93,26,'adaptive'),@('chess_cards_tab',1110,85,67,30,'adaptive'),@('yixing_row',71,440,34,22,'adaptive'),@('passive_label',425,439,60,23,'adaptive'),@('secret_icon',559,369,47,49,'rgb'))
 }
 if ($Layout -eq 'yixing_ability_tooltip') {
  $regions=@(@('yixing_title',1156,78,49,29,'adaptive'),@('copy_heroes',1340,192,89,27,'adaptive'),@('passive_name',965,254,86,31,'adaptive_spatial'),@('secret_label',1270,291,43,29,'adaptive'),@('view_details',971,443,75,24,'adaptive'))
 }
 if ($Layout -eq 'yixing_skill_tab') {
  $regions=@(@('yixing_title',1156,78,49,29,'adaptive'),@('copy_heroes',1340,192,89,27,'adaptive'),@('skill_icon',1162,236,51,51,'rgb'),@('secret_label',1270,291,43,29,'adaptive'),@('exclusive_label',1374,291,43,29,'adaptive'))
 }
 if ($Layout -eq 'yixing_details') {
  $regions=@(@('yixing_title',1156,78,49,29,'adaptive'),@('classic_skin',1208,78,93,29,'adaptive'),@('equipped',690,796,73,31,'adaptive'),@('skills_tab',1268,137,48,29,'adaptive'))
 }
 if ($Layout -eq 'chess_collection') {
  $regions=@(@('collection_title',48,23,54,31,'adaptive'),@('players_tab',643,22,50,29,'adaptive'),@('strength_tab',757,22,50,29,'adaptive'),@('yixing_name',598,294,48,30,'adaptive'),@('yixing_portrait',591,136,64,80,'rgb'))
 }
 if ($Layout -in @('main_hub','main_hub_modes')) {
  $regions=@(@('chess_players',1189,722,47,29,'adaptive'),@('cards',1286,722,47,29,'adaptive'),@('formation',1381,722,47,29,'adaptive'),@('start',1188,771,231,58,'adaptive'))
 }
 if ($Layout -eq 'custom_results') {
  $regions=@(@('custom_result_title',24,20,223,35),@('composition_tab',1214,23,84,30),@('return_lobby',1253,808,86,30,'dark_adaptive'))
 }
 if ($Layout -eq 'ended_battle') {
  $regions=@(@('ranking_label',699,342,56,18),@('rank_six',598,359,249,88),@('exit_now',539,665,89,31,'adaptive'),@('spectate',823,665,86,31,'adaptive'))
 }
 if ($Layout -eq 'exit_confirmation') {
  $regions=@(@('prompt_title',437,265,58,31,'adaptive'),@('exit_explanation',438,329,565,42,'adaptive'),@('continue_waiting',540,522,86,31,'adaptive'),@('confirm_exit',824,521,87,31,'adaptive'))
 }
 if ($Layout -eq 'battle_settings') {
  $regions=@(@('graphics_tab',166,14,43,24,'adaptive'),@('device_load_label',150,94,253,32,'adaptive'),@('exit_battle',1123,808,90,31,'dark_adaptive'))
 }
 if ($Layout -eq 'battle_controls') {
  $regions=@(@('battle_settings',94,10,29,30,'adaptive'),@('own_portrait',54,769,58,61,'rgb'),@('statistics',1220,10,30,34,'adaptive'))
 }
 if ($Layout -eq 'encyclopedia') {
  $regions=@(@('encyclopedia_title',272,15,77,30,'adaptive'),@('novice_tab',121,61,37,27,'adaptive'),@('official_label',35,91,38,28,'adaptive'),@('encyclopedia_close',62,15,27,27,'adaptive'))
 }
 if ($Layout -in @('custom_lobby_ready','custom_lobby_start')) {
  $regions=@(@('lobby_title',633,11,188,30),@('room_settings',1389,24,37,38),@('start_game',1188,771,231,58))
  $index=0
  foreach($centerX in @(488,646,805,963,1121)){
   $index++
   $regions+=,@(('bot_avatar_'+$index),($centerX-28),351,56,56,'rgb')
   $regions+=,@(('bot_label_'+$index),($centerX-32),436,66,31,'adaptive')
  }
 }
 if ($Layout -in @('room_options','room_options_close')) {
  $regions=@(@('room_options_title',206,199,110,30),@('difficulty_label',234,534,164,30),@('room_options_close',1216,198,31,30))
  $optionNames=@('newbie','bronze','silver','gold','platinum','diamond','xingyao','wangzhe')
  for($i=0;$i -lt 8;$i++) {
   $column=$i%4;$row=[int][Math]::Floor($i/4)
   $labelX=@(490,688,887,1086)[$column];$labelY=503+64*$row
   $cx=@(601,799,998,1197)[$column];$cy=516+64*$row
   $regions+=,@(('difficulty_'+$optionNames[$i]),$labelX,$labelY,90,26,'adaptive')
   $bright=0
   for($dy=-6;$dy -le 6;$dy++){for($dx=-6;$dx -le 6;$dx++){$color=$bitmap.GetPixel(($cx+$dx),($cy+$dy));if($color.R -ge 80 -and $color.G -ge 80 -and $color.B -ge 80){$bright++}}}
   $settingsChoices+=@{name=$optionNames[$i];center=@($cx,$cy);selected=($bright -ge 150);bright_pixels=$bright}
  }
 }
 $matches=@()
 foreach ($region in $regions) {
  $cx=[int]$region[1];$cy=[int]$region[2];$rw=[int]$region[3];$rh=[int]$region[4]
  $referenceX=$cx;$referenceY=$cy;$sourceBitmap=$referenceBitmap
  if($region.Count -gt 7){$referenceX=[int]$region[6];$referenceY=[int]$region[7]}
  if($region.Count -gt 8 -and $region[8] -eq 'menu'){$sourceBitmap=$menuBitmap}
  if($region.Count -gt 5 -and $region[5] -eq 'adaptive_shift_x8') {
   $score=0.0;$bestOffset=0
   for($offset=-8;$offset -le 8;$offset++) {
    $value=[GameFrameNative]::SpatialScore($sourceBitmap,$bitmap,$referenceX,$referenceY,($cx+$offset),$cy,$rw,$rh,$false)
    if($value -gt $score){$score=$value;$bestOffset=$offset}
   }
   $matches+=@{name=$region[0];score=$score;positive_pixels=($rw*$rh);center=@(($cx+[int]($rw/2)),($cy+[int]($rh/2)));method='bounded_title_translation_x8';offset_x=$bestOffset}
   continue
  }
  if($region.Count -gt 5 -and $region[5] -in @('rgb_spatial','adaptive_spatial')) {
   $score=[GameFrameNative]::SpatialScore($sourceBitmap,$bitmap,$referenceX,$referenceY,$cx,$cy,$rw,$rh,($region[5] -eq 'rgb_spatial'))
   $matches+=@{name=$region[0];score=$score;positive_pixels=($rw*$rh);center=@(($cx+[int]($rw/2)),($cy+[int]($rh/2)));method=if($region[5] -eq 'rgb_spatial'){'symmetric_one_pixel_normalized_rgb_error'}else{'symmetric_one_pixel'}}
   continue
  }
  $intersection=0;$expected=0;$actual=0;$rgbMatches=0
  $rgbMode=($region.Count -gt 5 -and $region[5] -eq 'rgb')
  $adaptive=($region.Count -gt 5 -and $region[5] -in @('adaptive','dark_adaptive'))
  if($adaptive) {
   $minA=765;$maxA=0;$minB=765;$maxB=0
   for($dy=0;$dy -lt $rh;$dy++){for($dx=0;$dx -lt $rw;$dx++){
    $a=$sourceBitmap.GetPixel(($referenceX+$dx),($referenceY+$dy));$b=$bitmap.GetPixel(($cx+$dx),($cy+$dy))
    $va=[int]$a.R+[int]$a.G+[int]$a.B;$vb=[int]$b.R+[int]$b.G+[int]$b.B
    $minA=[Math]::Min($minA,$va);$maxA=[Math]::Max($maxA,$va);$minB=[Math]::Min($minB,$vb);$maxB=[Math]::Max($maxB,$vb)
   }}
   $thresholdA=($minA+$maxA)/2.0;$thresholdB=($minB+$maxB)/2.0
  }
  for($dy=0;$dy -lt $rh;$dy++) { for($dx=0;$dx -lt $rw;$dx++) {
   $a=$sourceBitmap.GetPixel(($referenceX+$dx),($referenceY+$dy));$b=$bitmap.GetPixel(($cx+$dx),($cy+$dy))
   if($rgbMode){if([Math]::Abs([int]$a.R-[int]$b.R) -le 12 -and [Math]::Abs([int]$a.G-[int]$b.G) -le 12 -and [Math]::Abs([int]$a.B-[int]$b.B) -le 12){$rgbMatches++};continue}
   $wa=($a.R -ge 210 -and $a.G -ge 210 -and $a.B -ge 210)
   $wb=($b.R -ge 210 -and $b.G -ge 210 -and $b.B -ge 210)
   if($adaptive){$wa=(($maxA-$minA) -ge 60 -and ([int]$a.R+[int]$a.G+[int]$a.B) -ge $thresholdA);$wb=(($maxB-$minB) -ge 60 -and ([int]$b.R+[int]$b.G+[int]$b.B) -ge $thresholdB)}
   if($region.Count -gt 5 -and $region[5] -eq 'dark_adaptive'){$wa=(($maxA-$minA) -ge 60 -and ([int]$a.R+[int]$a.G+[int]$a.B) -lt $thresholdA);$wb=(($maxB-$minB) -ge 60 -and ([int]$b.R+[int]$b.G+[int]$b.B) -lt $thresholdB)}
   if($wa){$expected++};if($wb){$actual++};if($wa -and $wb){$intersection++}
  }}
  $score=if(($actual+$expected) -gt 0){2.0*$intersection/($actual+$expected)}else{0.0}
  if($rgbMode){$score=[double]$rgbMatches/($rw*$rh);$expected=$rw*$rh}
  $matches+=@{name=$region[0];score=$score;positive_pixels=$expected;center=@(($cx+[int]($rw/2)),($cy+[int]($rh/2)))}
 }
 $slots=@()
 if ($Layout -eq 'yixing_character_confirm') {
  # Actual selected Bai Ge reference has 359/360 white annulus angles;
  # the observed unselected Yi Xing has 0/360. Sample only outside the portrait.
  $covered=0
  for($angle=0;$angle -lt 360;$angle++) {
   $radians=$angle*[Math]::PI/180;$found=$false
   foreach($radius in @(35,36,37)) {
    $sx=[int][Math]::Round(447+$radius*[Math]::Cos($radians));$sy=[int][Math]::Round(790+$radius*[Math]::Sin($radians))
    $pixel=$bitmap.GetPixel($sx,$sy)
    if($pixel.R -ge 210 -and $pixel.G -ge 210 -and $pixel.B -ge 210){$found=$true}
   }
   if($found){$covered++}
  }
  $matches+=@{name='selected_marker';score=($covered/360.0);positive_pixels=$covered;center=@(447,790);method='visible_white_selection_annulus'}
 }
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
 @{status='captured';image=$Output;captured_at=$captured;matches=$matches;layout=$Layout;room_slots=$slots;settings_choices=$settingsChoices} | ConvertTo-Json -Depth 5 -Compress
} finally {$graphics.Dispose();$bitmap.Dispose();$referenceBitmap.Dispose();if($null -ne $menuBitmap){$menuBitmap.Dispose()}}
