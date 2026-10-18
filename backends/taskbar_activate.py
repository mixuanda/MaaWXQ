"""One explicit Explorer-taskbar activation; game HWND is never impersonated."""
import ctypes as c
from ctypes import wintypes as w
import os,threading,time
from pathlib import PureWindowsPath
from backends.win32_single_click import WindowsClickPort,NativeUnavailable
from window_identity import inspect_window
from runtime.game_profile import inspect_game,executable_path

TASKBAR_CLASSES=('Shell_TrayWnd','Shell_SecondaryTrayWnd')
BUTTON_KEYS=('taskbar_hwnd','taskbar_pid','explorer_path','name','automation_id','class_name',
             'process_id','runtime_id','control_type','rectangle','point','point_root_hwnd')

def validate_button(button,profile):
    if (button['name']!=profile['title']+' - 1 个运行窗口'
            or button['automation_id']!='Appid: '+profile['executable_path']
            or button['class_name']!='Taskbar.TaskListButtonAutomationPeer'
            or button['control_type']!='ControlType.Button'
            or button['enabled'] is not True or button['offscreen'] is not False
            or button['process_id']!=button['taskbar_pid']
            or button['point_root_hwnd']!=button['taskbar_hwnd']):
        raise NativeUnavailable('taskbar_button_identity_or_visibility_changed')
    expected=PureWindowsPath(os.environ.get('SystemRoot',r'C:\Windows'))/'explorer.exe'
    if PureWindowsPath(button['explorer_path'])!=expected:
        raise NativeUnavailable('actual_explorer_process_required')
    rid=button['runtime_id']
    if not isinstance(rid,list) or len(rid)<2 or any(type(x) is not int for x in rid):
        raise NativeUnavailable('uia_runtime_identity_required')
    left,top,width,height=button['rectangle'];x,y=button['point']
    if (any(type(v) is not int for v in (left,top,width,height,x,y))
            or not 8<=width<=512 or not 8<=height<=256
            or not left+3<=x<left+width-3 or not top+3<=y<top+height-3):
        raise NativeUnavailable('point_not_inside_observed_button')
    return button

def same_button(first,second):
    return all(first[k]==second[k] for k in BUTTON_KEYS)

def select_button(snapshot,profile,game):
    candidates=[]
    for item in snapshot['matches']:
        try:candidates.append(validate_button(item,profile))
        except (KeyError,TypeError,ValueError,NativeUnavailable):continue
    if not candidates:raise NativeUnavailable('no_reliable_game_taskbar_button')
    if len({tuple(x['runtime_id']) for x in candidates})!=len(candidates):
        raise NativeUnavailable('ambiguous_taskbar_runtime_identity')
    center=(game['client']['screen_x']+game['client']['width']/2,
            game['client']['screen_y']+game['client']['height']/2)
    return min(candidates,key=lambda b:((b['point'][0]-center[0])**2+(b['point'][1]-center[1])**2,b['taskbar_hwnd']))

class TaskbarActivationPort(WindowsClickPort):
    def __init__(self,button,profile,game,observed_monotonic,foreground):
        super().__init__(inspect_window)
        self.button=validate_button(button,profile);self.profile=profile;self.game=game
        self.observed_monotonic=observed_monotonic;self.initial_foreground=foreground
        self.taskbar=inspect_window(button['taskbar_hwnd'],button['taskbar_pid'])
        if self.taskbar['class_name'] not in TASKBAR_CLASSES or not self.taskbar['process_started_at']:
            raise NativeUnavailable('real_taskbar_window_required')
        self.stopped=threading.Event();self.stop_lock=threading.Lock();self.stop_reason=None
        self.supervisor_done=threading.Event();self.supervisor=None;self.deadline=None
        self.attempted=False;self.down_attempted=False
        self._check_target()

    def stop(self,reason):
        with self.stop_lock:
            if not self.stopped.is_set():self.stop_reason=reason;self.stopped.set()

    def _check_target(self):
        now=time.monotonic()
        if self.stopped.is_set():raise NativeUnavailable('taskbar_stop_latched:'+str(self.stop_reason))
        if not 0<=now-self.observed_monotonic<=5:raise NativeUnavailable('taskbar_observation_stale')
        if self.deadline is not None and now>=self.deadline:raise NativeUnavailable('taskbar_deadline_expired')
        row=inspect_window(self.button['taskbar_hwnd'],self.button['taskbar_pid'])
        if (row['identity_version']!=self.taskbar['identity_version']
                or row['geometry_version']!=self.taskbar['geometry_version']
                or row['class_name'] not in TASKBAR_CLASSES or not row['visible'] or row['minimized']
                or PureWindowsPath(executable_path(row['pid']))!=PureWindowsPath(self.button['explorer_path'])):
            raise NativeUnavailable('taskbar_process_or_geometry_changed')
        game=inspect_game(self.game['hwnd'],self.game['pid'])
        if game['identity_version']!=self.game['identity_version'] or game['executable_path']!=self.profile['executable_path']:
            raise NativeUnavailable('destination_game_identity_changed')
        if not self.down_attempted:
            if self.foreground()!=self.initial_foreground:raise NativeUnavailable('foreground_changed_before_activation')
            x,y=self.button['point']
            hit=int(self.user.GetAncestor(self.user.WindowFromPoint(w.POINT(x,y)),2) or 0)
            if hit!=self.button['taskbar_hwnd']:raise NativeUnavailable('taskbar_point_obscured_or_changed')
            if self.open_attempted and self.user_activity_changed():raise NativeUnavailable('input_changed_before_activation')
        if self.open_attempted and not self.guard_healthy():raise NativeUnavailable('activation_guard_not_healthy')

    def arm(self):
        self._check_target()
        super().open(self.stop)
        self.deadline=time.monotonic()+5
        self._check_target()
        def watch():
            while not self.supervisor_done.wait(.02):
                try:self._check_target()
                except Exception as error:
                    self.stop(str(error));self.release_owned();break
        self.supervisor=threading.Thread(target=watch,name='maawxq-taskbar-activation-deadline',daemon=True)
        self.supervisor.start()

    def refresh_evidence(self,button,observed_monotonic):
        validate_button(button,self.profile)
        if not same_button(self.button,button):raise NativeUnavailable('taskbar_button_changed_before_click')
        self.button=button;self.observed_monotonic=observed_monotonic
        self._check_target()

    def click_once(self):
        self._require_owner()
        if self.deadline is None:raise NativeUnavailable('taskbar_not_armed')
        if self.attempted:raise NativeUnavailable('taskbar_one_click_budget_exhausted')
        self.attempted=True;self._check_target()
        x,y=self.button['point']
        left,top,width,height=[self.user.GetSystemMetrics(i) for i in (76,77,78,79)]
        if width<=1 or height<=1 or not (left<=x<left+width and top<=y<top+height):
            raise NativeUnavailable('taskbar_point_outside_virtual_desktop')
        events=(self.Input*2)()
        for event in events:event.type=0;event.mi.dwExtraInfo=self.token
        events[0].mi.dx=round((x-left)*65535/(width-1));events[0].mi.dy=round((y-top)*65535/(height-1))
        events[0].mi.dwFlags=0xC001;events[1].mi.dwFlags=2
        with self.ledger_lock:
            self._check_target()
            if any(self.user.GetAsyncKeyState(code)&0x8000 for code in range(1,256)):
                raise NativeUnavailable('held_input_before_taskbar_click')
            self.down_attempted=True;self.held=True;self.submission_outcome='uncertain'
            sent=int(self.user.SendInput(2,events,c.sizeof(self.Input)))
            self.held=sent==2;self.submitted_event_count=sent
            self.submission_outcome='down_submitted' if sent==2 else 'incomplete_down_batch'
        if sent!=2:
            self.release_owned();raise NativeUnavailable('taskbar_send_input_incomplete:'+str(sent))
        try:interrupted=self.stopped.wait(.060)
        finally:
            if not self.release_owned():raise NativeUnavailable('taskbar_owned_release_failed')
        self.submission_outcome='released_after_interrupt' if interrupted else 'down_and_owned_up_submitted'
        self.stop('one_activation_click_completed')
        return {'target_scope':'verified_explorer_taskbar_button','taskbar_hwnd':self.button['taskbar_hwnd'],
                'destination_game_hwnd':self.game['hwnd'],'point':[x,y],'native_down_count':sent,
                'native_owned_up_count':self.owned_release_last_raw_return,'held':self.held,
                'submission_outcome':self.submission_outcome,'stop_reason':self.stop_reason}

    def close(self):
        self.supervisor_done.set();self.stop('closed')
        if self.supervisor and self.supervisor.is_alive():
            self.supervisor.join(1)
            if self.supervisor.is_alive():self._cleanup_error('activation_supervisor_close_timeout')
        return super().close()
