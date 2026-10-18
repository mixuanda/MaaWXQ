param([Parameter(Mandatory=$true)][string]$Image,[Parameter(Mandatory=$true)][string]$Profile,[Parameter(Mandatory=$true)][string]$Output,[string]$Cache)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
if(Test-Path -LiteralPath $Output){throw 'ocr_output_exists'}
$wall=[Diagnostics.Stopwatch]::StartNew()
$layout=Get-Content -LiteralPath $Profile -Raw -Encoding UTF8 | ConvertFrom-Json
if($layout.schema_version -ne 'strategy-ocr-layout/1' -or $layout.regions.Count -lt 1 -or $layout.regions.Count -gt 32){throw 'unsupported_ocr_layout'}
if(@($layout.regions.name | Select-Object -Unique).Count -ne $layout.regions.Count){throw 'duplicate_ocr_region'}
function File-Hash([string]$Path){
 $algorithm=[Security.Cryptography.SHA256]::Create();$inputStream=[IO.File]::OpenRead($Path)
 try{return ([BitConverter]::ToString($algorithm.ComputeHash($inputStream))).Replace('-','').ToLowerInvariant()}
 finally{$inputStream.Dispose();$algorithm.Dispose()}
}
$imageHash=File-Hash $Image
$profileHash=File-Hash $Profile
$cached=@{}
if($Cache){
 $old=Get-Content -LiteralPath $Cache -Raw -Encoding UTF8 | ConvertFrom-Json
 if($old.schema_version -eq 'strategy-region-ocr/1'){
  foreach($item in $old.regions){if($item.name -like 'shop_*_name'){$cached[$item.cache_key]=$item}}
 }
}
Add-Type -AssemblyName System.Runtime.WindowsRuntime
[void][Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime]
[void][Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime]
[void][Windows.Graphics.Imaging.BitmapDecoder,Windows.Graphics.Imaging,ContentType=WindowsRuntime]
[void][Windows.Graphics.Imaging.BitmapTransform,Windows.Foundation,ContentType=WindowsRuntime]
[void][Windows.Storage.Streams.Buffer,Windows.Storage.Streams,ContentType=WindowsRuntime]
[void][Windows.Storage.Streams.DataReader,Windows.Storage.Streams,ContentType=WindowsRuntime]
$asyncMethod=[System.WindowsRuntimeSystemExtensions].GetMethods()|Where-Object {$_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'}|Select-Object -First 1
function Await-Operation($Operation,[Type]$Type){
 $task=$asyncMethod.MakeGenericMethod($Type).Invoke($null,@($Operation))
 if(-not $task.Wait(8000)){throw 'ocr_async_timeout'}
 return $task.Result
}
$stream=$null;$sha=[Security.Cryptography.SHA256]::Create()
try {
 $language=[Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages|Where-Object {$_.LanguageTag -eq 'zh-Hans-CN' -or $_.LanguageTag -eq 'zh-CN'}|Select-Object -First 1
 if($null -eq $language){throw 'chinese_ocr_unavailable'}
 $engine=[Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($language)
 if($null -eq $engine){throw 'ocr_engine_unavailable'}
 $file=Await-Operation ([Windows.Storage.StorageFile]::GetFileFromPathAsync((Resolve-Path -LiteralPath $Image).ProviderPath)) ([Windows.Storage.StorageFile])
 $stream=Await-Operation ($file.OpenReadAsync()) ([Windows.Storage.Streams.IRandomAccessStreamWithContentType])
 $decoder=Await-Operation ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
 if($decoder.PixelWidth -ne $layout.width -or $decoder.PixelHeight -ne $layout.height){throw 'ocr_geometry_not_reviewed'}
 $rows=@();$hits=0
 foreach($region in $layout.regions){
  $regionTimer=[Diagnostics.Stopwatch]::StartNew()
  $x=[int]$region.bounds[0];$y=[int]$region.bounds[1];$width=[int]$region.bounds[2];$height=[int]$region.bounds[3];$scale=[int]$region.scale
  if($region.bounds.Count -ne 4 -or $scale -lt 1 -or $scale -gt 3 -or $x -lt 0 -or $y -lt 0 -or $width -lt 1 -or $height -lt 1 -or ($x+$width) -gt $decoder.PixelWidth -or ($y+$height) -gt $decoder.PixelHeight -or $width*$scale -gt 2400 -or $height*$scale -gt 2400){throw 'invalid_ocr_region'}
  $transform=[Windows.Graphics.Imaging.BitmapTransform]::new()
  $transform.ScaledWidth=[uint32]($decoder.PixelWidth*$scale);$transform.ScaledHeight=[uint32]($decoder.PixelHeight*$scale)
  $transform.InterpolationMode=[Windows.Graphics.Imaging.BitmapInterpolationMode]::NearestNeighbor
  $bounds=[Windows.Graphics.Imaging.BitmapBounds]::new()
  $bounds.X=[uint32]($x*$scale);$bounds.Y=[uint32]($y*$scale);$bounds.Width=[uint32]($width*$scale);$bounds.Height=[uint32]($height*$scale)
  $transform.Bounds=$bounds;$bitmap=$null;$reader=$null
  try {
   $bitmap=Await-Operation ($decoder.GetSoftwareBitmapAsync([Windows.Graphics.Imaging.BitmapPixelFormat]::Bgra8,[Windows.Graphics.Imaging.BitmapAlphaMode]::Premultiplied,$transform,[Windows.Graphics.Imaging.ExifOrientationMode]::IgnoreExifOrientation,[Windows.Graphics.Imaging.ColorManagementMode]::DoNotColorManage)) ([Windows.Graphics.Imaging.SoftwareBitmap])
   $buffer=[Windows.Storage.Streams.Buffer]::new([uint32]($bitmap.PixelWidth*$bitmap.PixelHeight*4))
   $bitmap.CopyToBuffer($buffer)
   $reader=[Windows.Storage.Streams.DataReader]::FromBuffer($buffer)
   $pixels=New-Object byte[] $buffer.Length;$reader.ReadBytes($pixels)
   $pixelHash=([BitConverter]::ToString($sha.ComputeHash($pixels))).Replace('-','').ToLowerInvariant()
   $cacheKey=$region.name+':'+$pixelHash+':'+($region.bounds -join ',')+':'+$scale+':'+$language.LanguageTag+':'+[Environment]::OSVersion.Version.ToString()
   $hit=$region.name -like 'shop_*_name' -and $cached.ContainsKey($cacheKey)
   if($hit){$text=$cached[$cacheKey].text;$lines=$cached[$cacheKey].lines;$hits++}
   else {
    $result=Await-Operation ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
    $text=$result.Text;$lines=@()
    foreach($line in $result.Lines){
     $words=@()
     foreach($word in $line.Words){$box=$word.BoundingRect;$words+=@{text=$word.Text;x=$x+$box.X/$scale;y=$y+$box.Y/$scale;width=$box.Width/$scale;height=$box.Height/$scale}}
     $lines+=@{text=$line.Text;words=$words}
    }
   }
   $rows+=@{name=$region.name;bounds=$region.bounds;scale=$scale;text=$text;lines=$lines;pixel_sha256=$pixelHash;cache_key=$cacheKey;cache_hit=$hit;elapsed_ms=$regionTimer.Elapsed.TotalMilliseconds}
  }finally{if($null -ne $reader){$reader.Dispose()};if($null -ne $bitmap){$bitmap.Dispose()}}
 }
 if((File-Hash $Image) -ne $imageHash){throw 'source_changed_during_ocr'}
 $record=@{schema_version='strategy-region-ocr/1';profile_sha256=$profileHash;image_sha256=$imageHash;width=$decoder.PixelWidth;height=$decoder.PixelHeight;language=$language.LanguageTag;regions=$rows;cache_hits=$hits;elapsed_ms=$wall.Elapsed.TotalMilliseconds;confidence_calibrated=$false;capture_calls=0;input_calls=0}
 [IO.File]::WriteAllText($Output,($record|ConvertTo-Json -Depth 10 -Compress),[Text.UTF8Encoding]::new($false))
 @{status='recognized';regions=$rows.Count;cache_hits=$hits;output=$Output;input_calls=0;capture_calls=0}|ConvertTo-Json -Compress
}finally{if($null -ne $stream){$stream.Dispose()};$sha.Dispose()}
