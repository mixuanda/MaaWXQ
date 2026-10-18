using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;
using System.Collections.Generic;
// Perception of saved/live pixels only; no desktop or input methods.
public static class ArmyPixels {
 public sealed class Match { public bool Known;public double Score,Margin,Scale;public int X,Y,Width,Height; }
 public sealed class Component {public bool Known;public int X,Y,Width,Height,CenterX,CenterY,Pixels;}
 sealed class Raster {
  public int W,H;public int[] Data;
  public Raster(Bitmap b) {W=b.Width;H=b.Height;Data=new int[W*H];
   var r=b.LockBits(new Rectangle(0,0,W,H),ImageLockMode.ReadOnly,PixelFormat.Format32bppArgb);
   try {for(int y=0;y<H;y++)Marshal.Copy(IntPtr.Add(r.Scan0,y*r.Stride),Data,y*W,W);}finally{b.UnlockBits(r);}
  }
  public double[] Sample(double x,double y,double width,double height) {
   var a=new double[288];int n=0;
   for(int yy=0;yy<12;yy++)for(int xx=0;xx<8;xx++) {
    double px=Math.Max(0,Math.Min(W-2,x+(xx+.5)*width/8)),py=Math.Max(0,Math.Min(H-2,y+(yy+.5)*height/12));
    int ix=(int)px,iy=(int)py;double fx=px-ix,fy=py-iy;
    int p=Data[iy*W+ix],q=Data[iy*W+ix+1],r=Data[(iy+1)*W+ix],s=Data[(iy+1)*W+ix+1];
    foreach(int shift in new int[]{16,8,0})a[n++]=((((p>>shift)&255)*(1-fx)+((q>>shift)&255)*fx)*(1-fy)+(((r>>shift)&255)*(1-fx)+((s>>shift)&255)*fx)*fy);
   }return a;
  }
 }
 static double Corr(double[] a,double[] b) {
  double am=0,bm=0;for(int i=0;i<a.Length;i++){am+=a[i];bm+=b[i];}am/=a.Length;bm/=b.Length;
  double ab=0,aa=0,bb=0;for(int i=0;i<a.Length;i++){double x=a[i]-am,y=b[i]-bm;ab+=x*y;aa+=x*x;bb+=y*y;}
  return aa<100||bb<100?0:ab/Math.Sqrt(aa*bb);
 }
 public static Match FindHand(Bitmap reference,Bitmap current,int sx,int sy,int width,int height) {
  var src=new Raster(reference).Sample(sx,sy,width,height);var target=new Raster(current);
  var peaks=new List<Match>();var best=new Match{Score=-1};
  foreach(double scale in new double[]{.90,1,1.10})for(int y=780;y<=812;y+=4)for(int x=280;x<=1240-width;x+=3) {
   double score=Corr(src,target.Sample(x,y,width*scale,height*scale));
   if(score>.7)peaks.Add(new Match{Score=score,X=x,Y=y,Scale=scale,Width=width,Height=height});
   if(score>best.Score)best=new Match{Score=score,X=x,Y=y,Scale=scale,Width=width,Height=height};
  }
  var seed=best;
  for(int y=seed.Y-4;y<=seed.Y+4;y++)for(int x=seed.X-3;x<=seed.X+3;x++)foreach(double scale in new double[]{.85,.90,.925,.95,.975,1,1.025,1.05,1.075,1.10,1.15}) {
   double score=Corr(src,target.Sample(x,y,width*scale,height*scale));
   if(score>best.Score)best=new Match{Score=score,X=x,Y=y,Scale=scale,Width=width,Height=height};
  }
  double second=0;foreach(var p in peaks)if(Math.Abs(p.X-best.X)>55)second=Math.Max(second,p.Score);
  best.Margin=best.Score-second;best.Known=best.Score>=.94&&best.Margin>=.10;return best;
 }
 public static Component NewUnit(Bitmap before,Bitmap after,int left,int top,int width,int height) {
  var a=new Raster(before);var b=new Raster(after);var changed=new bool[width*height];var seen=new bool[changed.Length];
  for(int y=0;y<height;y++)for(int x=0;x<width;x++) {
   int p=a.Data[(top+y)*a.W+left+x],q=b.Data[(top+y)*b.W+left+x];
   changed[y*width+x]=Math.Abs(((p>>16)&255)-((q>>16)&255))+Math.Abs(((p>>8)&255)-((q>>8)&255))+Math.Abs((p&255)-(q&255))>90;
  }
  var result=new Component();var queue=new Queue<int>();
  for(int i=0;i<changed.Length;i++)if(changed[i]&&!seen[i]) {
   queue.Enqueue(i);seen[i]=true;int count=0,minx=width,miny=height,maxx=0,maxy=0,sumx=0,sumy=0;
   while(queue.Count>0){int at=queue.Dequeue(),x=at%width,y=at/width;count++;sumx+=x;sumy+=y;minx=Math.Min(x,minx);maxx=Math.Max(x,maxx);miny=Math.Min(y,miny);maxy=Math.Max(y,maxy);
    for(int dy=-1;dy<=1;dy++)for(int dx=-1;dx<=1;dx++){int nx=x+dx,ny=y+dy;if(nx<0||ny<0||nx>=width||ny>=height)continue;int next=ny*width+nx;if(changed[next]&&!seen[next]){seen[next]=true;queue.Enqueue(next);}}
   }
   if(count>result.Pixels)result=new Component{Pixels=count,X=left+minx,Y=top+miny,Width=maxx-minx+1,Height=maxy-miny+1,CenterX=left+sumx/count,CenterY=top+sumy/count};
  }
  result.Known=result.Pixels>=250&&result.Width>=20&&result.Width<=180&&result.Height>=30&&result.Height<=175;
  return result;
 }
}
