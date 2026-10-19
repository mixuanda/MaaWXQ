// Standalone bitmap checks only. No desktop, capture, focus or input APIs.
using System;
using System.Drawing;
using System.Globalization;

public static class NameMaskChecks {
 static int checks;
 static void Check(string name,bool passed){if(!passed)throw new Exception("failed:"+name);checks++;}
 static Bitmap Canvas(Color background){var b=new Bitmap(1450,869);using(var g=Graphics.FromImage(b))g.Clear(background);return b;}
 static void Name(Bitmap b,int dx,int dy,Color ink){
  for(int glyph=0;glyph<7;glyph++)for(int y=4;y<22;y++)for(int x=0;x<8;x++)
   if(x<2||x>=6||y==4||y==12||y==21)b.SetPixel(149+glyph*12+x+dx,191+y+dy,ink);
 }
 static NameMaskCandidate.Result Compare(Bitmap a,Bitmap b){return NameMaskCandidate.Compare(a,b,144,191,100,31);}
 static string Json(NameMaskCandidate.Result r){return String.Format(CultureInfo.InvariantCulture,
  "{{\"Score\":{0:R},\"Dx\":{1},\"Dy\":{2},\"ReferencePixels\":{3},\"CurrentPixels\":{4}}}",r.Score,r.Dx,r.Dy,r.ReferencePixels,r.CurrentPixels);}
 public static int Main(string[] args){
  try{
   if(args.Length==2){using(var a=new Bitmap(args[0]))using(var b=new Bitmap(args[1])){
    if(a.Width!=1450||a.Height!=869||b.Width!=1450||b.Height!=869)throw new Exception("unsupported_geometry");
    Console.WriteLine(Json(Compare(a,b)));}return 0;}
   if(args.Length!=0)throw new Exception("expected_no_args_or_reference_and_current_images");
   using(var a=Canvas(Color.FromArgb(20,35,60))){
    Name(a,0,0,Color.White);Check("same_mask",Compare(a,a).Score>=.97);
    using(var b=Canvas(Color.FromArgb(20,35,60))){Name(b,3,-2,Color.White);Check("bounded_shift",Compare(a,b).Score>=.97);}
    using(var b=Canvas(Color.FromArgb(60,85,100))){Name(b,0,0,Color.FromArgb(200,200,190));Check("dark_background_and_white_ink_variation",Compare(a,b).Score>=.97);}
    using(var b=Canvas(Color.Black)){for(int y=24;y<30;y++)for(int x=5;x<85;x++)b.SetPixel(144+x,191+y,Color.White);Check("different_mask",Compare(a,b).Score<.97);}
    using(var b=Canvas(Color.Black)){Check("no_ink",Compare(a,b).Score==0);}
    using(var b=Canvas(Color.White)){Check("dense_mask",Compare(a,b).Score==0);}
    using(var b=Canvas(Color.Black)){Name(b,0,0,Color.FromArgb(255,155,155));Check("saturated_nonwhite_ink",Compare(a,b).Score==0);}
   }
   Console.WriteLine("{\"synthetic_bitmap_checks\":"+checks+",\"passed\":true,\"input_calls\":0,\"capture_calls\":0}");return 0;
  }catch(Exception e){Console.Error.WriteLine(e.Message);return 1;}
 }
}
