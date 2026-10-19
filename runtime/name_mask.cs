using System;
using System.Drawing;
// Candidate saved-pixel recognizer only. No input, capture or window APIs.
public static class NameMaskCandidate {
 public sealed class Result {public double Score;public int Dx,Dy,ReferencePixels,CurrentPixels;}
 static bool White(Color p){return p.R>=150&&p.G>=150&&p.B>=150&&Math.Max(p.R,Math.Max(p.G,p.B))-Math.Min(p.R,Math.Min(p.G,p.B))<=45;}
 static bool[,] Mask(Bitmap b,int x,int y,int w,int h,out int count){
  var m=new bool[w,h];count=0;for(int yy=0;yy<h;yy++)for(int xx=0;xx<w;xx++){m[xx,yy]=White(b.GetPixel(x+xx,y+yy));if(m[xx,yy])count++;}return m;
 }
 public static Result Compare(Bitmap reference,Bitmap current,int x,int y,int w,int h){
  int ac;var a=Mask(reference,x,y,w,h,out ac);var best=new Result{ReferencePixels=ac};
  if(ac<40||ac>w*h*.65)return best;
  for(int oy=-3;oy<=3;oy++)for(int ox=-3;ox<=3;ox++){
   int bc;var b=Mask(current,x+ox,y+oy,w,h,out bc);if(bc<40||bc>w*h*.65)continue;
   int matched=0;
   for(int dir=0;dir<2;dir++){var first=dir==0?a:b;var second=dir==0?b:a;
    for(int yy=0;yy<h;yy++)for(int xx=0;xx<w;xx++)if(first[xx,yy]){
     bool found=false;for(int dy=-1;dy<=1&&!found;dy++)for(int dx=-1;dx<=1;dx++){
      int tx=xx+dx,ty=yy+dy;if(tx>=0&&tx<w&&ty>=0&&ty<h&&second[tx,ty]){found=true;break;}}
     if(found)matched++;
    }
   }
   double score=(double)matched/(ac+bc);if(score>best.Score)best=new Result{Score=score,Dx=ox,Dy=oy,ReferencePixels=ac,CurrentPixels=bc};
  }return best;
 }
}
