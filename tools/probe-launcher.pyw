"""Small independent Tk launcher for the already-installed manual HD2 statistics probe."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import sys
import tkinter as tk
from tkinter import messagebox, ttk
import traceback

from probe_session import Session

LABELS = ('站立基线', '移动后', '自行装弹后', '提供辅助装弹后', '接受辅助装弹后')
FOLDER = Path(os.environ['LOCALAPPDATA']) / 'HD2Runtime/mod_data'


class App:
    def __init__(self, root, session=None):
        self.root, self.session = root, session or Session()
        self.timer = None
        self.rendered_rows = None
        root.title('HD2 小型统计探针')
        root.geometry('700x575')
        root.minsize(640, 550)
        root.configure(bg='#101a20')
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('TFrame', background='#101a20')
        style.configure('TLabel', background='#101a20', foreground='#e9eef0', font=('Microsoft YaHei UI', 10))
        style.configure('Title.TLabel', foreground='#f5d648', font=('Microsoft YaHei UI', 18, 'bold'))
        style.configure('Muted.TLabel', foreground='#acbbc2')
        style.configure('TButton', font=('Microsoft YaHei UI', 10), padding=(12, 7))
        style.configure('Start.TButton', background='#f5d648', foreground='#101a20', font=('Microsoft YaHei UI', 11, 'bold'))
        content = ttk.Frame(root, padding=22)
        content.pack(fill='both', expand=True)
        ttk.Label(content, text='关闭 Codex 后，也能收集测试数据', style='Title.TLabel').pack(anchor='w')
        ttk.Label(content, text='只采集小型统计表 · 每 30 秒一次 · 最长 15 分钟',
                  style='Muted.TLabel').pack(anchor='w', pady=(6, 16))
        actions = ttk.Frame(content)
        actions.pack(fill='x')
        self.start_button = ttk.Button(actions, text='启动游戏并自动采集', style='Start.TButton', command=self.start)
        self.start_button.pack(side='left')
        self.stop_button = ttk.Button(actions, text='停止采集', command=self.stop)
        self.stop_button.pack(side='left', padx=10)
        self.status = tk.StringVar(value=self.session.status)
        ttk.Label(content, textvariable=self.status, wraplength=620).pack(anchor='w', pady=(14, 6))
        self.count = tk.StringVar(value='尚未采集')
        ttk.Label(content, textvariable=self.count, style='Muted.TLabel').pack(anchor='w')
        ttk.Separator(content).pack(fill='x', pady=16)
        ttk.Label(content, text='需要对照某个动作时：选标签，动作完成后采集一次。').pack(anchor='w')
        manual = ttk.Frame(content)
        manual.pack(fill='x', pady=(8, 12))
        self.label = tk.StringVar(value=LABELS[0])
        self.labels = ttk.Combobox(manual, textvariable=self.label, values=LABELS, width=31)
        self.labels.pack(side='left', fill='x', expand=True)
        self.capture_button = ttk.Button(manual, text='采集一次', command=self.capture)
        self.capture_button.pack(side='left', padx=(10, 0))
        self.results = tk.Listbox(content, height=5, bg='#182730', fg='#d9e3e7', borderwidth=0,
                                  highlightthickness=0, font=('Microsoft YaHei UI', 10))
        self.results.pack(fill='both', expand=True)
        bottom = ttk.Frame(content)
        bottom.pack(fill='x', pady=(12, 0))
        ttk.Button(bottom, text='打开结果文件夹', command=self.open_results).pack(side='left')
        ttk.Label(content, text='保留此窗口到游戏退出，会自动停用探针。关闭窗口会停止采集，游戏继续。',
                  style='Muted.TLabel', wraplength=620).pack(anchor='w', pady=(10, 0))
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.refresh()
        self.timer = root.after(1000, self.tick)

    def start(self):
        if not self.session.start(launch_game=True):
            self.status.set(self.session.last_error or self.session.status)
        self.refresh()

    def capture(self):
        if not self.session.capture(self.label.get().strip()):
            self.status.set(self.session.last_error or self.session.status)
        self.refresh()

    def stop(self):
        self.session.stop()
        self.refresh()

    def refresh(self):
        self.status.set(self.session.last_error or self.session.status)
        records = self.session.captures
        failed = sum(bool(item.get('error')) for item in records)
        saved = sum(item.get('status') == 'saved' for item in records)
        self.count.set('成功 %d 份 · 未就绪/失败 %d 份%s' % (
            saved, failed, ' · 正在等待一份结果' if self.session.pending else ''))
        active = self.session.state in ('waiting', 'running')
        self.start_button.configure(state='disabled' if active else 'normal')
        self.stop_button.configure(state='normal' if active or self.session.pending else 'disabled')
        self.capture_button.configure(state='disabled' if self.session.pending or self.session.state == 'waiting' else 'normal')
        rows = tuple((item.get('label', ''), item.get('error', ''), item.get('status', 'pending')) for item in records[-5:])
        if rows != self.rendered_rows:
            self.results.delete(0, 'end')
            for label, error, status in rows:
                wording = '已保存' if status == 'saved' else ('等待中' if status == 'pending' else '未完成')
                self.results.insert('end', wording + ' · ' + label + (' · ' + error if error else ''))
            self.rendered_rows = rows

    def tick(self):
        try:
            self.session.tick()
            self.refresh()
        except Exception as error:
            self.session.stop()
            self.status.set('启动器错误：' + str(error))
            write_error()
        self.timer = self.root.after(1000, self.tick)

    def open_results(self):
        target = self.session.index_path.parent if self.session.index_path else FOLDER
        target.mkdir(parents=True, exist_ok=True)
        os.startfile(str(target))

    def close(self):
        self.session.stop()
        if self.timer is not None:
            self.root.after_cancel(self.timer)
        self.root.destroy()


def write_error():
    FOLDER.mkdir(parents=True, exist_ok=True)
    with (FOLDER / 'probe_launcher_error.log').open('a', encoding='utf8') as output:
        output.write(traceback.format_exc() + '\n')


def acquire_instance():
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    api.CreateMutexW.restype = ctypes.c_void_p
    api.CloseHandle.argtypes = [ctypes.c_void_p]
    ctypes.set_last_error(0)
    handle = api.CreateMutexW(None, False, 'Local\\HD2WarCostLedgerProbeLauncher')
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == 183:
        api.CloseHandle(handle)
        return None
    return api, handle


def lower_priority():
    # JSON conversion runs here, outside the game, with scheduling priority below the game.
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.GetCurrentProcess.restype = ctypes.c_void_p
    api.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    api.SetPriorityClass.restype = ctypes.c_int
    return bool(api.SetPriorityClass(api.GetCurrentProcess(), 0x00004000))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        class Fake:
            status = '尚未启动'; state = 'idle'; last_error = None
            captures = []; pending = None; index_path = None
            def start(self, launch_game=True): self.state = 'waiting'; self.status = '等待游戏'; return True
            def capture(self, label): self.captures.append({'label': label, 'path': 'fixture', 'status': 'saved'}); return True
            def stop(self): self.state = 'stopped'; self.status = '已停止'; return True
            def tick(self): pass
        root = tk.Tk(); root.withdraw()
        fake = Fake(); app = App(root, fake)
        app.start_button.invoke(); assert fake.state == 'waiting'
        app.stop_button.invoke(); assert fake.state == 'stopped'
        app.label.set('提供辅助装弹后'); app.capture_button.invoke()
        assert fake.captures[0]['label'] == '提供辅助装弹后'
        assert app.results.get(0) == '已保存 · 提供辅助装弹后'
        root.update_idletasks(); app.close()
        print('PASS: actual Tk window construction, button commands, labels and rendering; no game launch or real store writes.')
        return
    lock = acquire_instance()
    if lock is None:
        root = tk.Tk(); root.withdraw()
        messagebox.showinfo('HD2 探针', '探针启动器已经打开，请使用已有窗口。')
        root.destroy(); return
    try:
        lower_priority()
        root = tk.Tk()
        App(root)
        root.mainloop()
    finally:
        lock[0].CloseHandle(lock[1])


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        write_error()
        messagebox.showerror('HD2 探针启动失败', str(error) + '\n详情：' + str(FOLDER / 'probe_launcher_error.log'))
