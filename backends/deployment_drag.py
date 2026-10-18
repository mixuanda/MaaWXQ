"""One explicitly typed 300ms drag inside a freshly bound custom-game client."""
from dataclasses import dataclass
import ctypes as c
from ctypes import wintypes as w
import time,math
import threading
from datetime import datetime,timezone
from backends.game_click import GameClickPort,GameClickBroker,GameClickEvidence,NativeUnavailable
from runtime.cleanup import close_verified
from strategy.codec import timestamp

@dataclass(frozen=True)
class DeployEvidence(GameClickEvidence):
 end_x:int=0
 end_y:int=0
 hero_id:str=''
 match_id:str=''
 capture_utc:str=''
 source_match:float=0
 empty_board_match:float=0
 capacity_match:float=0
 capacity:int=0
 occupied:int=-1
 phase_match:float=0
 phase_margin:float=0
 purchase_verified:bool=False

class DeploymentDragPort(GameClickPort):
 def __init__(self,observer,binding,executable_path,abort_event,destination):
  super().__init__(observer,binding,executable_path,abort_event)
  self.destination=destination;self.drag_moves=[];self.gesture='one_bounded_drag_300ms/1'
 def click(self,hwnd,x,y,permit):
  self._require_owner()
  if not self.guard_healthy():raise NativeUnavailable('native_guard_not_healthy')
  left,top,width,height=[self.user.GetSystemMetrics(i)for i in (76,77,78,79)]
  ex=self.binding.screen_x+self.destination[0];ey=self.binding.screen_y+self.destination[1]
  if width<=1 or height<=1:raise NativeUnavailable('invalid_virtual_desktop')
  def move_event(px,py):
   if not(left<=px<left+width and top<=py<top+height):raise NativeUnavailable('outside_virtual_desktop')
   event=self.Input();event.type=0;event.mi.dwExtraInfo=self.token
   event.mi.dx=round((px-left)*65535/(width-1));event.mi.dy=round((py-top)*65535/(height-1));event.mi.dwFlags=0xC001
   return event
  def check(px,py,holding=False):
   self.validate_native_target(hwnd)
   if (self.foreground()!=hwnd or int(self.user.GetAncestor(self.user.WindowFromPoint(w.POINT(px,py)),2)or 0)!=hwnd
       or any(self.user.GetAsyncKeyState(k)&0x8000 for k in range(1,256)if not(holding and k==1))
       or not permit()):raise NativeUnavailable('drag_target_or_permission_changed')
  events=(self.Input*2)();events[0]=move_event(x,y);events[1].type=0;events[1].mi.dwFlags=0x0002;events[1].mi.dwExtraInfo=self.token
  try:
   with self.ledger_lock:
    check(x,y);self.held=True;self.submission_outcome='uncertain'
    sent=int(self.user.SendInput(2,events,c.sizeof(self.Input)));self.held=sent==2;self.submitted_event_count=sent
    if sent!=2:
     self.submission_outcome='drag_down_batch_incomplete'
     raise NativeUnavailable('drag_down_incomplete:'+str(sent))
    self.down_submitted_at=time.monotonic();self.submission_outcome='drag_down_submitted'
   if self.abort_event.wait(.06):raise NativeUnavailable('drag_revoked_before_move')
   for step in range(1,11):
    px=round(x+(ex-x)*step/10);py=round(y+(ey-y)*step/10)
    with self.ledger_lock:
     if not self.held:raise NativeUnavailable('drag_owned_hold_already_released')
     check(px,py,True);event=move_event(px,py)
     attempt={'step':step,'x':px,'y':py,'raw_return':None};self.drag_moves.append(attempt)
     try:raw=int(self.user.SendInput(1,c.byref(event),c.sizeof(self.Input)))
     except BaseException:
      self.submission_outcome='drag_move_outcome_uncertain'
      raise
     attempt['raw_return']=raw
     if raw!=1:raise NativeUnavailable('drag_move_incomplete')
    if self.abort_event.wait(.024):raise NativeUnavailable('drag_revoked_during_move')
   self.submission_outcome='drag_path_submitted_requires_visual_verification'
  finally:
   if not self.release_owned():raise NativeUnavailable('drag_owned_release_failed')
  return 13

class DeploymentDragBroker(GameClickBroker):
 def __init__(self,evidence,*,observer,enabled=False,utc_clock=None,**options):
  self.utc_clock=utc_clock or(lambda:datetime.now(timezone.utc))
  for name,maximum in [('max_age',5),('max_seconds',2)]:
   value=options.setdefault(name,maximum)
   if type(value)not in(int,float)or not math.isfinite(value)or not 0<value<=maximum:
    raise ValueError('bounded_deployment_'+name+'_required')
  super().__init__(evidence,observer=observer,enabled=enabled,**options)
  self.port_factory=lambda obs:DeploymentDragPort(obs,evidence.binding,evidence.executable_path,self.stopped,(evidence.end_x,evidence.end_y))
 def _check(self):
  observed=super()._check()
  if not 0<=(self.utc_clock()-timestamp(self.evidence.capture_utc)).total_seconds()<=5:
   raise NativeUnavailable('deployment_source_utc_stale_or_future')
  return observed
 def click_once(self):
  raise NativeUnavailable('explicit_drag_once_required')
 def drag_once(self):
  receipt=super().click_once()
  return receipt|{'operation':'deploy_owned_hand_hero','gesture':'one_bounded_drag_300ms/1',
                  'game_postcondition_verified':False,'blind_retry_allowed':False}
 def validate_context(self):
  e=self.evidence
  try:age=(self.utc_clock()-timestamp(e.capture_utc)).total_seconds()
  except (ValueError,TypeError,AttributeError):raise NativeUnavailable('deployment_capture_time_required')
  if (not isinstance(e,DeployEvidence)or e.context!='custom_deployment' or e.operation!='deploy_owned_hand_hero'
      or e.scene!='preparation_empty_own_board'or e.recognizer!='owned-hero-and-empty-board/1'
      or not isinstance(e.hero_id,str)or not e.hero_id.strip()or e.hero_id=='unknown'
      or not isinstance(e.match_id,str)or not e.match_id.strip()or e.match_id=='unknown'
      or e.no_other_humans_verified is not True or e.purchase_verified is not True
      or type(e.occupied)is not int or type(e.capacity)is not int or e.occupied!=0 or e.capacity!=3
      or any(type(v)not in (int,float)or not math.isfinite(v)or not 0<=v<=1 for v in [e.source_match,e.empty_board_match,e.capacity_match,e.phase_match,e.phase_margin])
      or e.source_match<.92 or e.empty_board_match<.97 or e.capacity_match<.97 or e.phase_match<.97 or e.phase_margin<.02
      or any(type(v)is not int for v in(e.x,e.y,e.end_x,e.end_y))
      or not(400<=e.x<=1240 and 765<=e.y<=855)or (e.end_x,e.end_y)!=(710,555)
      or(e.binding.width,e.binding.height)!=(1450,869)
      or e.binding.class_name!='UnityWndClass'or not e.executable_path.casefold().endswith('\\wxq.exe')
      or len(e.frame_sha256)!=64 or any(ch not in '0123456789abcdef'for ch in e.frame_sha256)
      or not 0<=age<=5):
   raise NativeUnavailable('unproven_or_stale_deployment_context')

def guarded_executor(evidence,*,observer,enabled=False,utc_clock=None):
 """Create one consumed-on-attempt callback. No native port opens by default."""
 owner=threading.get_ident();attempted=False
 def execute():
  nonlocal attempted
  if threading.get_ident()!=owner:raise ValueError('deployment_executor_requires_single_owner_thread')
  if attempted:raise ValueError('deployment_attempt_consumed_no_retry')
  attempted=True
  broker=DeploymentDragBroker(evidence,observer=observer,enabled=enabled,utc_clock=utc_clock)
  cleaned=False
  try:
   broker.arm();receipt=broker.drag_once();summary,_=close_verified(broker);cleaned=True
   return receipt|{'cleanup_confirmed':True,'native_summary':summary,'drag_moves':list(broker.port.drag_moves),
                   'game_postcondition_verified':False,'blind_retry_allowed':False}
  finally:
   if not cleaned:broker.close()
 return execute
