param([string]$Image,[string]$Output)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
if(Test-Path -LiteralPath $Output){throw 'ocr_output_exists'}
Add-Type -AssemblyName System.Runtime.WindowsRuntime
[void][Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime]
[void][Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime]
[void][Windows.Graphics.Imaging.BitmapDecoder,Windows.Graphics.Imaging,ContentType=WindowsRuntime]
$asyncMethod=[System.WindowsRuntimeSystemExtensions].GetMethods()|Where-Object {$_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'}|Select-Object -First 1
function Await-Operation($Operation,[Type]$Type){
 $task=$asyncMethod.MakeGenericMethod($Type).Invoke($null,@($Operation))
 if(-not $task.Wait(8000)){throw 'ocr_async_timeout'}
 return $task.Result
}
$stream=$null;$bitmap=$null
try {
 $languages=@([Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages|ForEach-Object {$_.LanguageTag})
 $language=$languages|Where-Object {$_ -eq 'zh-Hans-CN' -or $_ -eq 'zh-CN'}|Select-Object -First 1
 if(-not $language){throw ('chinese_ocr_unavailable:'+($languages -join ','))}
 $file=Await-Operation ([Windows.Storage.StorageFile]::GetFileFromPathAsync($Image)) ([Windows.Storage.StorageFile])
 $stream=Await-Operation ($file.OpenReadAsync()) ([Windows.Storage.Streams.IRandomAccessStreamWithContentType])
 $decoder=Await-Operation ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
 $bitmap=Await-Operation ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
 $engine=[Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new($language))
 if($null -eq $engine){throw 'ocr_engine_unavailable'}
 $result=Await-Operation ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
 $lines=@()
 foreach($line in $result.Lines){
  $words=@()
  foreach($word in $line.Words){$box=$word.BoundingRect;$words+=@{text=$word.Text;x=$box.X;y=$box.Y;width=$box.Width;height=$box.Height}}
  $lines+=@{text=$line.Text;words=$words}
 }
 $record=@{status='recognized';language=$language;image=$Image;image_sha256=(Get-FileHash -LiteralPath $Image -Algorithm SHA256).Hash.ToLowerInvariant();text=$result.Text;lines=$lines;input_calls=0}
 $json=$record|ConvertTo-Json -Depth 8 -Compress
 [IO.File]::WriteAllText($Output,$json,[Text.UTF8Encoding]::new($false))
 @{status='recognized';output=$Output;lines=$lines.Count;language=$language;input_calls=0}|ConvertTo-Json -Compress
}finally{if($null -ne $bitmap){$bitmap.Dispose()};if($null -ne $stream){$stream.Dispose()}}
