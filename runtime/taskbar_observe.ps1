param([Parameter(Mandatory=$true)][string]$GameTitle,[Parameter(Mandatory=$true)][string]$GameExe,[Parameter(Mandatory=$true)][string]$CaptureDirectory)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName WindowsBase
Add-Type -AssemblyName System.Drawing
Add-Type -TypeDefinition @'
using System;using System.Collections.Generic;using System.Text;using System.Runtime.InteropServices;
public static class GameTaskbarObserve {
 [StructLayout(LayoutKind.Sequential)] public struct POINT {public int X,Y;public POINT(int x,int y){X=x;Y=y;}}
 public delegate bool EnumProc(IntPtr h,IntPtr p);
 [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc callback,IntPtr p);
 [DllImport("user32.dll",CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr h,StringBuilder text,int size);
 [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h,out uint pid);
 [DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(POINT p);
 [DllImport("user32.dll")] public static extern IntPtr GetAncestor(IntPtr h,uint flag);
 [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
 [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
 public static long[] Handles() {
  var result=new List<long>();EnumWindows((h,p)=>{var name=new StringBuilder(256);GetClassName(h,name,256);
   if(name.ToString()=="Shell_TrayWnd"||name.ToString()=="Shell_SecondaryTrayWnd")result.Add(h.ToInt64());return true;},IntPtr.Zero);
  return result.ToArray();
 }
}
'@
[void][GameTaskbarObserve]::SetProcessDPIAware()
if(-not (Test-Path -LiteralPath $CaptureDirectory -PathType Container)){throw 'New private capture directory required'}
$condition=[Windows.Automation.PropertyCondition]::new([Windows.Automation.AutomationElement]::AutomationIdProperty,('Appid: '+$GameExe))
$candidateCount=0
$nameMatchedCount=0
$rows=@(foreach($handle in [GameTaskbarObserve]::Handles()) {
 $root=[Windows.Automation.AutomationElement]::FromHandle([IntPtr]$handle)
 if($null -eq $root){continue}
 $elements=$root.FindAll([Windows.Automation.TreeScope]::Descendants,$condition)
 foreach($element in $elements) {
  $candidateCount++
  $name=$element.Current.Name
  if(-not $name.StartsWith($GameTitle+' - ')){continue}
  $nameMatchedCount++
  if($nameMatchedCount -gt 2){throw 'Unsupported number of matching taskbar buttons'}
  $rect=$element.Current.BoundingRectangle
  $point=[Windows.Point]::new(0,0)
  $clickable=$element.TryGetClickablePoint([ref]$point)
  if(-not $clickable){$point=[Windows.Point]::new(($rect.Left+$rect.Width/2),($rect.Top+$rect.Height/2))}
  $px=[int][Math]::Round($point.X);$py=[int][Math]::Round($point.Y)
  $atPoint=[Windows.Automation.AutomationElement]::FromPoint([Windows.Point]::new($px,$py))
  $hitMatched=$false
  for($depth=0;$depth -lt 8 -and $null -ne $atPoint;$depth++) {
   if([Windows.Automation.Automation]::Compare($element,$atPoint)){$hitMatched=$true;break}
   $atPoint=[Windows.Automation.TreeWalker]::ControlViewWalker.GetParent($atPoint)
  }
  $pointRoot=[GameTaskbarObserve]::GetAncestor([GameTaskbarObserve]::WindowFromPoint([GameTaskbarObserve+POINT]::new($px,$py)),2).ToInt64()
  [uint32]$ownerId=0
  [void][GameTaskbarObserve]::GetWindowThreadProcessId([IntPtr]$handle,[ref]$ownerId)
  $process=Get-Process -Id $ownerId
  $left=[int][Math]::Floor($rect.Left);$top=[int][Math]::Floor($rect.Top)
  $width=[int][Math]::Ceiling($rect.Width);$height=[int][Math]::Ceiling($rect.Height)
  if($width -lt 8 -or $height -lt 8 -or $width -gt 512 -or $height -gt 256){throw 'Unexpected taskbar button bounds'}
  $image=Join-Path $CaptureDirectory ('button-'+$handle+'.png')
  if(Test-Path -LiteralPath $image){throw 'Taskbar observation path already used'}
  $bitmap=[Drawing.Bitmap]::new($width,$height);$graphics=[Drawing.Graphics]::FromImage($bitmap)
  try{$graphics.CopyFromScreen($left,$top,0,0,[Drawing.Size]::new($width,$height));$bitmap.Save($image,[Drawing.Imaging.ImageFormat]::Png)}
  finally{$graphics.Dispose();$bitmap.Dispose()}
  [pscustomobject]@{taskbar_hwnd=$handle;taskbar_pid=$ownerId;explorer_path=$process.Path;
   name=$name;automation_id=$element.Current.AutomationId;class_name=$element.Current.ClassName;
   process_id=$element.Current.ProcessId;runtime_id=@($element.GetRuntimeId());
   control_type=$element.Current.ControlType.ProgrammaticName;enabled=$element.Current.IsEnabled;offscreen=$element.Current.IsOffscreen;
   rectangle=@($left,$top,$width,$height);point=@($px,$py);point_source=$(if($clickable){'uia_clickable_point'}else{'observed_rectangle_center'});point_root_hwnd=$pointRoot;point_matches_element=$hitMatched;
   image=$image;image_sha256=(Get-FileHash -LiteralPath $image -Algorithm SHA256).Hash.ToLowerInvariant()}
 }
})
@{observed_at=[DateTimeOffset]::UtcNow.ToString('o');foreground_hwnd=[GameTaskbarObserve]::GetForegroundWindow().ToInt64();matches=$rows;input_calls=0;candidate_count=$candidateCount;name_match_count=$nameMatchedCount;requested_title=$GameTitle;requested_executable=$GameExe}|ConvertTo-Json -Depth 6 -Compress
