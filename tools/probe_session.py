"""Small external controller for the existing one-shot, read-only Lua probe.

The controller polls process names every two seconds. It never reads game memory
or starts tasklist helpers. The game's existing probe performs a capture only
when this controller publishes one request file.
"""
from __future__ import annotations

import ctypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import time
import uuid

try:
    from .probe_decode import read_binary
except ImportError:
    from probe_decode import read_binary


STORE_NAME = 'mods_hd2_costs_war_cost_ledger.json'
REQUEST_NAME = 'ledger_probe_request.json'
PROCESS_INTERVAL = 2.0
CAPTURE_INTERVAL = 30.0
WAIT_TIMEOUT = 300.0
RESPONSE_TIMEOUT = 45.0
INITIAL_DELAY = 30.0
FIRST_RESPONSE_TIMEOUT = 120.0
SESSION_DURATION = 900.0
MAX_CAPTURES = 31
NOT_READY_ERRORS = {'local player unavailable', 'PLAYER_NOT_FOUND', 'SCORE_UNREADABLE'}
PERFORMANCE_NAME = re.compile(r'^HD2Performance-(\d{8}T\d{6}Z)-(\d+)-\d+\.log$')


def default_folder() -> Path:
    return Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local')) / 'HD2Runtime/mod_data'


def _timestamp(value):
    if type(value) in (int, float):
        return value
    try:
        date = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return date.timestamp()
    except (ValueError, TypeError):
        return None


def game_processes() -> tuple[int, ...]:
    """Return HD2 PIDs via the read-only Windows process snapshot API."""
    if os.name != 'nt':
        raise OSError('这个启动器需要 Windows。')
    from ctypes import wintypes

    class ProcessEntry(ctypes.Structure):
        _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD),
                    ('th32ProcessID', wintypes.DWORD), ('th32DefaultHeapID', ctypes.c_size_t),
                    ('th32ModuleID', wintypes.DWORD), ('cntThreads', wintypes.DWORD),
                    ('th32ParentProcessID', wintypes.DWORD), ('pcPriClassBase', wintypes.LONG),
                    ('dwFlags', wintypes.DWORD), ('szExeFile', wintypes.WCHAR * 260)]

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    kernel.Process32FirstW.restype = wintypes.BOOL
    kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    kernel.Process32NextW.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.CreateToolhelp32Snapshot(0x00000002, 0)  # TH32CS_SNAPPROCESS
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(entry)
        if not kernel.Process32FirstW(handle, ctypes.byref(entry)):
            raise ctypes.WinError(ctypes.get_last_error())
        found = []
        while True:
            if entry.szExeFile.casefold() == 'helldivers2.exe':
                found.append(int(entry.th32ProcessID))
            if not kernel.Process32NextW(handle, ctypes.byref(entry)):
                error = ctypes.get_last_error()
                if error != 18:  # ERROR_NO_MORE_FILES
                    raise ctypes.WinError(error)
                break
        return tuple(found)
    finally:
        kernel.CloseHandle(handle)


def launch_game() -> None:
    os.startfile('steam://run/553850')


def _write_json(path: Path, data: dict, exclusive: bool = False) -> None:
    """Publish a complete JSON file; exclusive requests never replace others."""
    pending = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        pending.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf8')
        if exclusive:
            os.link(pending, path)
        else:
            os.replace(pending, path)
    finally:
        pending.unlink(missing_ok=True)


def _read_object(path: Path) -> dict:
    data = json.loads(path.read_text(encoding='utf8')) if path.exists() else {}
    if not isinstance(data, dict):
        raise ValueError('JSON 不是对象：' + str(path))
    return data


class Session:
    """A GUI-friendly session. Call tick() approximately once per second.

    start/capture/stop return bool; user-facing failures are in last_error.
    After stop(), keep ticking until the game exits to disable the cached probe
    setting safely. No store writes are allowed while any HD2 process exists.
    """
    def __init__(self, folder: Path | None = None, processes=None, launch=None,
                 clock=time.monotonic, wall_clock=None, performance_folder: Path | None = None):
        self.folder = Path(folder) if folder is not None else default_folder()
        self.store_path = self.folder / STORE_NAME
        self.request_path = self.folder / REQUEST_NAME
        self.index_path: Path | None = None
        self.state = 'idle'
        self.status = '尚未启动采集。'
        self.last_error = ''
        self.captures: list[dict] = []
        self._processes = processes or game_processes
        self._launch = launch or launch_game
        self._clock = clock
        self._wall_clock = wall_clock or (lambda: datetime.now(timezone.utc).isoformat())
        self.performance_folder = Path(performance_folder) if performance_folder is not None else (
            Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local')) / 'CowboyBingus/Helldivers2/Logs')
        self.performance_logs: list[dict] = []
        self._known_pids: set[int] = set()
        self._started_timestamp = None
        self._ended_at = None
        self._last_process_check = float('-inf')
        self._pids: tuple[int, ...] = ()
        self._session_id = None
        self._started_at = None
        self._wait_started = None
        self._game_started = None
        self._next_capture = None
        self._pending: dict | None = None
        self._pending_since = None
        self._automatic = False
        self._needs_disable = False
        self._saw_game = False
        self._backup_path = None
        self.enabled = False

    @property
    def pending(self) -> dict | None:
        return self._pending

    def _running(self, force: bool = False) -> bool:
        now = self._clock()
        if force or now - self._last_process_check >= PROCESS_INTERVAL:
            self._pids = tuple(self._processes())
            self._known_pids.update(self._pids)
            self._last_process_check = now
        return bool(self._pids)

    def _save_index(self) -> None:
        if self.index_path is None:
            return
        self._reference_performance_logs()
        _write_json(self.index_path, {'version': 2, 'id': self._session_id,
            'started_at': self._started_at, 'updated_at': str(self._wall_clock()),
            'ended_at': self._ended_at,
            'state': self.state, 'status': self.status, 'last_error': self.last_error,
            'game_pids': list(self._pids), 'observed_game_pids': sorted(self._known_pids),
            'store_backup': str(self._backup_path) if self._backup_path else None,
            'captures': self.captures, 'performance_logs': self.performance_logs})

    def _reference_performance_logs(self) -> None:
        """Reference existing recorder files only; no extra recorder or copies."""
        try:
            if not self.performance_folder.is_dir():
                return
            references = {item['path']: item for item in self.performance_logs}
            for path in self.performance_folder.glob('HD2Performance-*.log'):
                match = PERFORMANCE_NAME.fullmatch(path.name)
                if not match:
                    continue
                pid = int(match[2])
                created = datetime.strptime(match[1], '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc)
                after_start = self._started_timestamp is not None and created.timestamp() >= self._started_timestamp
                pid_matches = pid in self._known_pids
                if not after_start and not pid_matches:
                    continue
                try:
                    information = path.stat()
                except OSError:
                    continue
                references[str(path)] = {'path': str(path), 'pid': pid,
                    'created_at': created.isoformat(), 'modified_at': datetime.fromtimestamp(information.st_mtime, timezone.utc).isoformat(),
                    'size': information.st_size, 'referenced_at': str(self._wall_clock()),
                    'matched_by': (['created_after_start'] if after_start else []) + (['pid'] if pid_matches else [])}
            self.performance_logs = list(references.values())
        except (OSError, ValueError):
            # Unavailable optional recorder logs do not stop stat capture.
            return

    def _new_index(self) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        folder = self.folder / 'probe_sessions'
        folder.mkdir(exist_ok=True)
        self._session_id = uuid.uuid4().hex
        self._started_at = str(self._wall_clock())
        self._started_timestamp = _timestamp(self._started_at)
        self._ended_at = None
        self._known_pids = set(self._pids)
        self.performance_logs = []
        self.index_path = folder / (self._session_id + '.json')
        self.captures = []
        self.last_error = ''
        self._backup_path = None

    def _enable(self) -> None:
        if self._running(force=True):
            if _read_object(self.store_path).get('probe_enabled') is not True:
                raise ValueError('游戏已运行，但探针未在启动前启用；关闭游戏后重新启动采集。')
            self.enabled = True
            return
        data = _read_object(self.store_path)
        if self.store_path.exists():
            self._backup_path = self.store_path.with_name(self.store_path.stem + '.' + uuid.uuid4().hex + '.bak.json')
            with self._backup_path.open('xb') as backup:
                backup.write(self.store_path.read_bytes())
        # Recheck immediately before writing; never overwrite the in-game cached store.
        if self._running(force=True):
            raise ValueError('游戏刚刚启动，未修改账目设置；关闭游戏后重试。')
        data['probe_enabled'] = True
        _write_json(self.store_path, data)
        self.enabled = True

    def _disable_if_closed(self) -> bool:
        if not self._needs_disable or self._running(force=True):
            return False
        # Use the newest ledger: a backup restore would destroy match results.
        data = _read_object(self.store_path)
        data['probe_enabled'] = False
        if self._running(force=True):
            return False
        _write_json(self.store_path, data)
        self._needs_disable = False
        self.enabled = False
        return True

    def _cancel_pending(self, reason: str, status: str = 'cancelled') -> None:
        if self._pending is None:
            return
        # Only remove the request this session owns; leave any replacement alone.
        if self.request_path.exists():
            request = _read_object(self.request_path)
            if request.get('id') == self._pending['id']:
                self.request_path.unlink()
        self._pending['status'] = status
        self._pending['error'] = reason
        self._pending['finished_at'] = str(self._wall_clock())
        self._pending = None
        self._pending_since = None

    def _failure(self, message: str) -> bool:
        self.last_error = message
        self.status = message
        self.state = 'error'
        self._ended_at = str(self._wall_clock())
        self._automatic = False
        try:
            self._cancel_pending(message, 'error')
            self._disable_if_closed()
            self._save_index()
        except (OSError, ValueError) as error:
            self.last_error += '；清理失败：' + str(error)
            self.status = self.last_error
        return False

    def start(self, launch_game: bool = True) -> bool:
        if self._automatic or self._pending is not None:
            self.last_error = '本次采集仍在运行；先停止后再启动。'
            return False
        try:
            if self.request_path.exists():
                raise ValueError('已有一条待采集命令，未覆盖。请先检查或处理原命令。')
            self._new_index()
            self._enable()
            self._needs_disable = True
            self._wait_started = self._clock()
            self._game_started = None
            self._next_capture = None
            self._saw_game = False
            self._automatic = True
            if self._running(force=True):
                self._begin_game()
            else:
                self.state = 'waiting'
                self.status = '探针已启用，等待游戏启动（最多 5 分钟）。'
                self._save_index()
                if launch_game:
                    self._launch()
            return True
        except (OSError, ValueError) as error:
            return self._failure(str(error))

    def _begin_game(self) -> None:
        self._saw_game = True
        self._game_started = self._clock()
        self._next_capture = self._game_started + INITIAL_DELAY
        self.state = 'running'
        self.status = '游戏已启动，30 秒后开始；每 30 秒采集一次，最多 15 分钟。'
        self._save_index()

    def _request(self, label: str) -> None:
        if not self._running(force=True):
            raise ValueError('游戏尚未运行，未发送采集命令。')
        if self._pending is not None or self.request_path.exists():
            raise ValueError('已有一条待采集命令，未重复发送。')
        if not isinstance(label, str) or len(label.encode('utf8')) > 160:
            raise ValueError('标签最多 160 UTF-8 字节。')
        if len(self.captures) >= MAX_CAPTURES:
            raise ValueError('本次已达到 31 份采集上限。')
        capture_id = uuid.uuid4().hex
        include_code = not any(item.get('has_code') for item in self.captures)
        request = {'id': capture_id, 'label': label, 'include_code': include_code, 'format': 'binary'}
        item = {**request, 'path': str(self.folder / ('ledger_probe_' + capture_id + '.json')),
            'status': 'pending', 'error': None, 'requested_at': str(self._wall_clock())}
        _write_json(self.request_path, request, exclusive=True)
        self.captures.append(item)
        self._pending = item
        self._pending_since = self._clock()
        self.status = '已请求采集：' + label
        self._save_index()

    def capture(self, label: str) -> bool:
        """Add one labelled sample while HD2 is running, with no store changes."""
        try:
            if not self._running(force=True):
                raise ValueError('游戏尚未运行，未发送采集命令。')
            if _read_object(self.store_path).get('probe_enabled') is not True:
                raise ValueError('探针未在启动前启用；游戏运行中不会修改账目设置。')
            if self._pending is not None or self.request_path.exists():
                self.last_error = '已有一条待采集命令，未重复发送。'
                return False
            if self.index_path is None:
                self._new_index()
            self._needs_disable = True
            self.enabled = True
            self._saw_game = True
            self._request(label)
            self.last_error = ''
            if not self._automatic:
                self.state = 'running'
                self._save_index()
            return True
        except (OSError, ValueError) as error:
            # Bad manual labels must not cancel an otherwise healthy auto session.
            self.last_error = str(error)
            return False

    def _collect_response(self) -> None:
        if self._pending is None:
            return
        path = Path(self._pending['path'])
        binary_path = path.with_suffix('.bin')
        response = None
        if binary_path.exists():
            decode_started = time.perf_counter()
            response = read_binary(binary_path)
            self._pending['external_decode_ms'] = (time.perf_counter() - decode_started) * 1000
            if response.get('id') != self._pending['id']:
                raise ValueError('二进制采集结果 id 不匹配，未写入 JSON。')
            encode_started = time.perf_counter()
            _write_json(path, response)
            self._pending['external_json_ms'] = (time.perf_counter() - encode_started) * 1000
            self._pending['binary_path'] = str(binary_path)
        if path.exists():
            # An externally expanded JSON may exceed the game's binary cap;
            # the validated raw table still has at most 4096 + 64*16 entries.
            if response is None:
                if path.stat().st_size > 1048576:
                    raise ValueError('采集结果超过 1 MiB，未接受该结果。')
                response = _read_object(path)
            if response.get('id') != self._pending['id']:
                raise ValueError('采集结果 id 不匹配，未接受该结果。')
            if response.get('error') is not None and not isinstance(response['error'], str):
                raise ValueError('采集结果 error 格式无效。')
            if response.get('stats') is not None and not isinstance(response['stats'], dict):
                raise ValueError('采集结果 stats 格式无效。')
            item = self._pending
            error = response.get('error') or (None if response.get('stats') else '采集没有有效 stats。')
            item['status'] = 'error' if error else 'saved'
            item['error'] = str(error) if error else None
            item['finished_at'] = str(self._wall_clock())
            item['mission'] = response.get('mission')
            item['has_code'] = bool(response.get('code'))
            self._pending = None
            self._pending_since = None
            # A completed result can exist just before Lua removes its request.
            if self.request_path.exists():
                request = _read_object(self.request_path)
                if request.get('id') == item['id']:
                    self.request_path.unlink()
            self.status = '已保存 %d 份；最近：%s' % (sum(c['status'] == 'saved' for c in self.captures), item['label'])
            self._save_index()
            if error:
                if error in NOT_READY_ERRORS and self._automatic:
                    self.status = '游戏统计尚未就绪；30 秒后再试。'
                    self._next_capture = self._clock() + CAPTURE_INTERVAL
                    self._save_index()
                else:
                    raise ValueError('采集失败：' + str(error))
        elif self._clock() - self._pending_since >= (FIRST_RESPONSE_TIMEOUT if len(self.captures) == 1 else RESPONSE_TIMEOUT):
            timeout = FIRST_RESPONSE_TIMEOUT if len(self.captures) == 1 else RESPONSE_TIMEOUT
            raise ValueError('%d 秒未收到探针结果；已停止自动采集，未继续堆积命令。' % timeout)

    def tick(self) -> None:
        try:
            running = self._running()
            self._collect_response()
            if not running:
                if self._saw_game:
                    self._automatic = False
                    self._cancel_pending('游戏已退出。')
                    self._disable_if_closed()
                    self._saw_game = False
                    self.state = 'completed'
                    self._ended_at = str(self._wall_clock())
                    self.status = '游戏已退出；采集结束，探针已停用，账目已保留。'
                    self._save_index()
                elif self._automatic and self._clock() - self._wait_started >= WAIT_TIMEOUT:
                    self._failure('5 分钟内未检测到游戏启动；探针已停用。')
                elif self._needs_disable and self._disable_if_closed():
                    self.status = '采集已停止，游戏已关闭；探针已停用。'
                    self._save_index()
                return
            if not self._automatic:
                return
            if not self._saw_game:
                self._begin_game()
            elapsed = self._clock() - self._game_started
            if self._pending is not None:
                return
            if len(self.captures) >= MAX_CAPTURES or elapsed > SESSION_DURATION:
                self._automatic = False
                self.state = 'completed'
                self._ended_at = str(self._wall_clock())
                self.status = '自动采集已完成；等待游戏退出后停用探针。'
                self._save_index()
                return
            if self._clock() >= self._next_capture:
                label = 'baseline' if not any(c['status'] == 'saved' for c in self.captures) else 'auto-%02d' % (len(self.captures) + 1)
                self._request(label)
                # No catch-up loop if the controller was delayed.
                self._next_capture = self._clock() + CAPTURE_INTERVAL
        except (OSError, ValueError) as error:
            self._failure(str(error))

    def stop(self) -> bool:
        """Stop requests, keep game running, and disable only after game exit."""
        try:
            self._automatic = False
            self._cancel_pending('用户停止采集。')
            self.state = 'stopped'
            self._ended_at = str(self._wall_clock())
            if self._disable_if_closed():
                self.status = '采集已停止，探针已停用；账目已保留。'
            elif self._needs_disable:
                self.status = '采集已停止；请保留此窗口，游戏退出后会自动停用探针。'
            else:
                self.status = '采集已停止。'
            self._save_index()
            return True
        except (OSError, ValueError) as error:
            return self._failure(str(error))
