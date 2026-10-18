using System;
using System.Drawing;
using System.Collections.Generic;
// Saved-image perception only. No window, focus or input APIs.
public static class HandAppearance {
 public sealed class Match { public double Score,X,Y,Scale; }
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
 static Match Find(double[] source,Bitmap target,int x,int y,double w,double h,int radius,double[] scales) {
  var best=new Match{Score=-1};
  double step=scales.Length==1?.5:1;
  foreach(double scale in scales)for(double dy=-radius;dy<=radius;dy+=step)for(double dx=-radius;dx<=radius;dx+=step) {
   double s=Score(source,Sample(target,x+dx,y+dy,w*scale,h*scale));
   if(s>best.Score)best=new Match{Score=s,X=x+dx,Y=y+dy,Scale=scale};
  } return best;
 }
 public static Result Analyze(Bitmap before,Bitmap after,int slot,string[] heroes) {
  if(before.Width!=1450||before.Height!=869||after.Width!=1450||after.Height!=869||slot<0||slot>3||heroes.Length!=4)throw new Exception("unsupported_hand_geometry");
  int[] left={293,498,702,906};var r=new Result{Known=false,Reason="unverified",OfferScores=new double[4]};
  r.Passive=Find(Sample(before,610,774,97,70),after,556,774,97,70,3,new double[]{1});
  r.Equipment=Find(Sample(before,744,778,96,64),after,689,778,96,64,3,new double[]{1});
  for(int i=0;i<4;i++) {
   double[] source=Sample(before,left[i]+10,88,170,90);
   var match=Find(source,after,795,787,170,90,6,new double[]{.585,.595,.605,.615});
   r.OfferScores[i]=match.Score;if(i==slot)r.Received=match;
  }
  double[] expected=Sample(before,left[slot]+10,88,170,90);
  r.BeforePassiveHero=Find(expected,before,608,787,170,90,3,new double[]{.595,.605}).Score;
  r.BeforeEquipmentHero=Find(expected,before,741,787,170,90,3,new double[]{.595,.605}).Score;
  double other=-1;
  for(int i=0;i<4;i++)if(i!=slot&&heroes[i]!=heroes[slot])other=Math.Max(other,r.OfferScores[i]);
  r.DistinctHeroMargin=r.Received.Score-other;
  // Multiple independent constraints: both old cards move to the three-card layout,
  // the newly occupied position matches the purchased live shop art, and it was
  // absent from both old positions. Unknown competing labels never count as equal.
  r.Known=r.Passive.Score>=.97&&r.Equipment.Score>=.97&&r.Received.Score>=.92&&
   r.DistinctHeroMargin>=.12&&r.BeforePassiveHero<.75&&r.BeforeEquipmentHero<.75;
  if(r.Known){r.BeforeCount=2;r.AfterCount=3;r.Reason="two_preserved_cards_recentered_and_distinct_purchased_art_added";}
  else r.Reason="hand_transition_constraints_not_met";
  return r;
 }
}
