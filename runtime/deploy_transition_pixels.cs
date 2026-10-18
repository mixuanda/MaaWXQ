using System;
using System.Drawing;
using System.Collections.Generic;
// Saved-image perception only. No window, focus or input APIs.
public static class DeployTransitionPixels {
 public sealed class Component { public int Pixels,X,Y,Width,Height,CenterX,CenterY; public bool Known; }
 public sealed class HeroMatch { public bool Known; public double Score,OtherScore,Margin; public int Slot; }
 public sealed class Match { public double Score,X,Y,Scale,Skew; }
 public sealed class Result {
  public bool Known; public string Reason; public Match Passive,Equipment,Received;
  public double[] OfferScores; public double BeforePassiveHero,BeforeEquipmentHero;
  public double DistinctHeroMargin; public int BeforeCount,AfterCount;
 }
 static double[] Sample(Bitmap b,double x,double y,double w,double h) {
  var v=new double[24*16*3];int n=0;
  for(int yy=0;yy<16;yy++)for(int xx=0;xx<24;xx++) {
   double px=x+(xx+.5)*w/24,py=y+(yy+.5)*h/16;
   int ix=(int)px,iy=(int)py;double fx=px-ix,fy=py-iy;
   Color a=b.GetPixel(ix,iy),c=b.GetPixel(ix+1,iy),d=b.GetPixel(ix,iy+1),e=b.GetPixel(ix+1,iy+1);
   v[n++]=(a.R*(1-fx)+c.R*fx)*(1-fy)+(d.R*(1-fx)+e.R*fx)*fy;
   v[n++]=(a.G*(1-fx)+c.G*fx)*(1-fy)+(d.G*(1-fx)+e.G*fx)*fy;
   v[n++]=(a.B*(1-fx)+c.B*fx)*(1-fy)+(d.B*(1-fx)+e.B*fx)*fy;
  } return v;
 }
 static double Score(double[] a,double[] b) {
  double sa=0,sb=0;for(int i=0;i<a.Length;i++){sa+=a[i];sb+=b[i];}
  sa/=a.Length;sb/=b.Length;double aa=0,bb=0,ab=0;
  for(int i=0;i<a.Length;i++){double av=a[i]-sa,bv=b[i]-sb;aa+=av*av;bb+=bv*bv;ab+=av*bv;}
  return aa<1||bb<1?0:ab/Math.Sqrt(aa*bb);
 }
 static double[] SlantedSample(Bitmap b,double x,double y,double w,double h,double skew) {
  var v=new double[24*16*3];int n=0;
  for(int yy=0;yy<16;yy++)for(int xx=0;xx<24;xx++) {
   double px=x+(xx+.5)*w/24,py=y+(yy+.5)*h/16+(xx+.5)*skew/24;
   int ix=(int)px,iy=(int)py;double fx=px-ix,fy=py-iy;
   Color a=b.GetPixel(ix,iy),c=b.GetPixel(ix+1,iy),d=b.GetPixel(ix,iy+1),e=b.GetPixel(ix+1,iy+1);
   v[n++]=(a.R*(1-fx)+c.R*fx)*(1-fy)+(d.R*(1-fx)+e.R*fx)*fy;
   v[n++]=(a.G*(1-fx)+c.G*fx)*(1-fy)+(d.G*(1-fx)+e.G*fx)*fy;
   v[n++]=(a.B*(1-fx)+c.B*fx)*(1-fy)+(d.B*(1-fx)+e.B*fx)*fy;
  }return v;
 }
 static double[] CachedSlant(Bitmap target,double x,double y,double scale,double skew,Dictionary<string,double[]> cache) {
  string key=String.Format(System.Globalization.CultureInfo.InvariantCulture,"{0:R}:{1:R}:{2:R}:{3:R}",x,y,scale,skew);
  double[] value;if(!cache.TryGetValue(key,out value)){value=SlantedSample(target,x,y,170*scale,90*scale,skew);cache.Add(key,value);}return value;
 }
 static Match FindUnitCard(double[] source,Bitmap target,Dictionary<string,double[]> cache) {
  var best=new Match{Score=-1};
  foreach(double scale in new double[]{1.26,1.28,1.30})foreach(double skew in new double[]{0,4,8,12})
   // Owned-unit cards shift left when no generated card is stacked behind.
   // Both observed panel variants stay within this bounded left-panel range.
   for(int dy=-6;dy<=6;dy+=2)for(int dx=-24;dx<=8;dx+=2) {
    double score=Score(source,CachedSlant(target,73+dx,57+dy,scale,skew,cache));
    if(score>best.Score)best=new Match{Score=score,X=73+dx,Y=57+dy,Scale=scale,Skew=skew};
   }
  var seed=best;
  foreach(double ds in new double[]{-.01,0,.01})foreach(double dk in new double[]{-2,0,2})
   for(int dy=-1;dy<=1;dy++)for(int dx=-1;dx<=1;dx++) {
    double score=Score(source,CachedSlant(target,seed.X+dx,seed.Y+dy,seed.Scale+ds,seed.Skew+dk,cache));
    if(score>best.Score)best=new Match{Score=score,X=seed.X+dx,Y=seed.Y+dy,Scale=seed.Scale+ds,Skew=seed.Skew+dk};
   }
  return best;
 }
 static Match Find(double[] source,Bitmap target,int x,int y,double w,double h,int radius,double[] scales) {
  var best=new Match{Score=-1};
  double step=scales.Length==1?.5:1;
  foreach(double scale in scales)for(double dy=-radius;dy<=radius;dy+=step)for(double dx=-radius;dx<=radius;dx+=step) {
   double s=Score(source,Sample(target,x+dx,y+dy,w*scale,h*scale));
   if(s>best.Score)best=new Match{Score=s,X=x+dx,Y=y+dy,Scale=scale};
  } return best;
 }

 public static Component NewUnit(Bitmap before,Bitmap after) {
  const int left=610,top=435,width=200,height=175;
  var changed=new bool[width*height];var seen=new bool[width*height];
  for(int y=0;y<height;y++)for(int x=0;x<width;x++) {
   var a=before.GetPixel(left+x,top+y);var b=after.GetPixel(left+x,top+y);
   changed[y*width+x]=Math.Abs(a.R-b.R)+Math.Abs(a.G-b.G)+Math.Abs(a.B-b.B)>75;
  }
  var best=new Component();var queue=new Queue<int>();
  for(int i=0;i<changed.Length;i++)if(changed[i]&&!seen[i]) {
   queue.Enqueue(i);seen[i]=true;int count=0,minx=width,miny=height,maxx=0,maxy=0,sumx=0,sumy=0;
   while(queue.Count>0) {
    int at=queue.Dequeue(),x=at%width,y=at/width;count++;sumx+=x;sumy+=y;
    minx=Math.Min(minx,x);maxx=Math.Max(maxx,x);miny=Math.Min(miny,y);maxy=Math.Max(maxy,y);
    for(int dy=-1;dy<=1;dy++)for(int dx=-1;dx<=1;dx++) {
     int nx=x+dx,ny=y+dy;if(nx<0||ny<0||nx>=width||ny>=height)continue;
     int next=ny*width+nx;if(changed[next]&&!seen[next]){seen[next]=true;queue.Enqueue(next);}
    }
   }
   if(count>best.Pixels)best=new Component{Pixels=count,X=left+minx,Y=top+miny,Width=maxx-minx+1,Height=maxy-miny+1,CenterX=left+sumx/count,CenterY=top+sumy/count};
  }
  best.Known=best.Pixels>=250&&best.Width>=25&&best.Width<=180&&best.Height>=30&&best.Height<=165;
  return best;
 }
 public static HeroMatch UnitModel(Bitmap confirmed,Bitmap current) {
  double expected=Score(Sample(confirmed,646,495,88,46),Sample(current,646,495,88,46));
  return new HeroMatch{Known=expected>=.92,Score=expected,Slot=0};
 }
 public static HeroMatch Detail(Bitmap shop,Bitmap details,int slot,string[] heroes) {
  int[] left={293,498,702,906};double expected=-1,other=-1;
  var cache=new Dictionary<string,double[]>();
  for(int i=0;i<4;i++) {
   double score=FindUnitCard(Sample(shop,left[i]+10,88,170,90),details,cache).Score;
   if(i==slot)expected=score;else if(heroes[i]!=heroes[slot])other=Math.Max(other,score);
  }
  return new HeroMatch{Known=expected>=.92&&expected-other>=.12,Score=expected,OtherScore=other,Margin=expected-other,Slot=slot};
 }

 public static Result Analyze(Bitmap before,Bitmap after) {
  if(before.Width!=1450||before.Height!=869||after.Width!=1450||after.Height!=869)throw new Exception("unsupported_geometry");
  var r=new Result{Known=false,Reason="unverified"};
  r.Passive=Find(Sample(before,556,774,97,70),after,610,774,97,70,3,new double[]{1});
  r.Equipment=Find(Sample(before,689,778,96,64),after,744,778,96,64,3,new double[]{1});
  var hero=Sample(before,795,787,103,54);
  r.BeforePassiveHero=Find(hero,after,608,787,103,54,3,new double[]{1}).Score;
  r.BeforeEquipmentHero=Find(hero,after,741,787,103,54,3,new double[]{1}).Score;
  r.Known=r.Passive.Score>=.97&&r.Equipment.Score>=.97&&r.BeforePassiveHero<.75&&r.BeforeEquipmentHero<.75;
  if(r.Known){r.BeforeCount=3;r.AfterCount=2;r.Reason="both_preserved_cards_recentered_after_owned_hero_removed";}
  else r.Reason="three_to_two_hand_transition_not_proven";
  return r;
 }
}
