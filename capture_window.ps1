param([long]$TargetHwnd, [uint32]$ExpectedPid, [string]$OutputPath, [long]$MaxCacheBytes=67108864, [int]$MaxCacheFiles=50)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
Add-Type -AssemblyName System.Drawing
Add-Type @'
using System;
using System.Text;
using System.Runtime.InteropServices;
public static class WXQCapture {
 [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L,T,R,B; }
 [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X,Y; }
 [DllImport("user32.dll")] public static extern bool IsWindow(IntPtr h);
 [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
 [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
 [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint p);
 [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr h, out RECT r);
 [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr h, ref POINT p);
 [DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(POINT p);
 [DllImport("user32.dll")] public static extern IntPtr GetAncestor(IntPtr h, uint flags);
 [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder t, int n);
 [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint flags);
 [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
}
'@
$result = [ordered]@{status='capture_unavailable'; reason=$null; image=$null; method='PrintWindow-client'; visibility='unknown'; occlusion='unknown'}
$handle = [IntPtr]$TargetHwnd
$bitmap = $null
$graphics = $null
try {
 do {
  $cacheFolder = [IO.Path]::GetDirectoryName($OutputPath)
  $cacheFiles = @(Get-ChildItem -LiteralPath $cacheFolder -File -Recurse -Force -ErrorAction SilentlyContinue)
  $cacheBytes = ($cacheFiles | Measure-Object -Property Length -Sum).Sum
  if ($null -eq $cacheBytes) { $cacheBytes=0 }
  if ($MaxCacheBytes -le 0 -or $MaxCacheFiles -le 0) { $result.reason='invalid_cache_limits'; break }
  if ($cacheFiles.Count -ge $MaxCacheFiles -or $cacheBytes -ge $MaxCacheBytes) { $result.status='cache_limit_reached'; $result.reason='no_new_capture_written'; break }
  if (-not [WXQCapture]::IsWindow($handle)) { $result.reason='window_not_found'; break }
  [uint32]$actualPid = 0
  [void][WXQCapture]::GetWindowThreadProcessId($handle, [ref]$actualPid)
  if ($actualPid -ne $ExpectedPid) { $result.reason='window_identity_changed'; break }
  $title = [Text.StringBuilder]::new(1024)
  [void][WXQCapture]::GetWindowText($handle, $title, 1024)
  $result.title = $title.ToString()
  if (-not [WXQCapture]::IsWindowVisible($handle)) { $result.reason='window_hidden'; $result.visibility='hidden'; break }
  if ([WXQCapture]::IsIconic($handle)) { $result.reason='window_minimized'; $result.visibility='minimized'; break }
  $result.visibility='visible'
  [void][WXQCapture]::SetProcessDPIAware()
  $rect = [WXQCapture+RECT]::new()
  if (-not [WXQCapture]::GetClientRect($handle, [ref]$rect)) { $result.reason='bounds_unavailable'; break }
  $width = $rect.R - $rect.L
  $height = $rect.B - $rect.T
  if ($width -le 0 -or $height -le 0 -or $width -gt 8192 -or $height -gt 8192) { $result.reason='invalid_dimensions'; break }
  $result.width=$width; $result.height=$height
  $point = [WXQCapture+POINT]::new()
  $point.X=[int]($width/2); $point.Y=[int]($height/2)
  if ([WXQCapture]::ClientToScreen($handle, [ref]$point)) {
   $top = [WXQCapture]::GetAncestor([WXQCapture]::WindowFromPoint($point), 2)
   $root = [WXQCapture]::GetAncestor($handle, 2)
   $result.occlusion = if ($top -ne $root) {'center_obscured_or_offscreen'} else {'center_clear_other_regions_unknown'}
  }
  $bitmap = [Drawing.Bitmap]::new($width,$height)
  $graphics = [Drawing.Graphics]::FromImage($bitmap)
  $graphics.Clear([Drawing.Color]::Black)
  $dc = $graphics.GetHdc()
  try { $printed = [WXQCapture]::PrintWindow($handle,$dc,3) } finally { $graphics.ReleaseHdc($dc) }
  if (-not $printed) { $result.reason='printwindow_failed'; break }
  $colors = [Collections.Generic.HashSet[int]]::new()
  for ($y=0; $y -lt $height; $y += [Math]::Max(1,[int]($height/32))) {
   for ($x=0; $x -lt $width; $x += [Math]::Max(1,[int]($width/32))) { [void]$colors.Add($bitmap.GetPixel($x,$y).ToArgb()) }
  }
  $result.sampled_colors=$colors.Count
  if ($colors.Count -lt 8) { $result.status='blank_or_low_detail_frame'; $result.reason='heuristic_low_color_variation'; break }
  [uint32]$afterPid=0
  [void][WXQCapture]::GetWindowThreadProcessId($handle,[ref]$afterPid)
  if ($afterPid -ne $ExpectedPid) { $result.reason='window_identity_changed'; break }
  [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($OutputPath))
  $stream = [IO.MemoryStream]::new()
  try {
   $bitmap.Save($stream,[Drawing.Imaging.ImageFormat]::Png)
   $cacheFiles = @(Get-ChildItem -LiteralPath $cacheFolder -File -Recurse -Force -ErrorAction SilentlyContinue)
   $cacheBytes = ($cacheFiles | Measure-Object -Property Length -Sum).Sum
   if ($null -eq $cacheBytes) { $cacheBytes=0 }
   if ($cacheFiles.Count -ge $MaxCacheFiles -or ($cacheBytes+$stream.Length) -gt $MaxCacheBytes) { $result.status='cache_limit_reached'; $result.reason='new_frame_would_exceed_limit'; break }
   $fileStream = [IO.File]::Open($OutputPath,[IO.FileMode]::CreateNew)
   try { $stream.Position=0; $stream.CopyTo($fileStream) } finally { $fileStream.Dispose() }
  } finally { $stream.Dispose() }
  $result.status='candidate_requires_visual_review'
  $result.reason='pixel_variation_is_not_semantic_validation'
  $result.image=$OutputPath
 } while ($false)
} finally {
 if ($null -ne $graphics) {$graphics.Dispose()}
 if ($null -ne $bitmap) {$bitmap.Dispose()}
}
$result | ConvertTo-Json -Compress
