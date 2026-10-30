import json
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from . import backend
from .mapping import BUTTONS, EXTRAS, load_profile, validate

class Window:
    def __init__(self, root, profile_path):
        self.root = root
        self.worker = None
        self.stop = threading.Event()
        self.messages = queue.Queue()
        self.closing = False
        self.profile = load_profile(profile_path)
        root.title('SteamBridge — Steam Controller for Arch Linux')
        root.geometry('730x850')
        root.minsize(640, 740)
        panel = ttk.Frame(root, padding=22)
        panel.pack(fill='both', expand=True)
        ttk.Label(panel, text='SteamBridge', font=('', 23, 'bold')).pack(anchor='w')
        ttk.Label(panel, text='Steam Controller (2026) → virtual Xbox gamepad').pack(anchor='w', pady=(3, 14))
        self.state = tk.StringVar(value='Ready. Exit Steam, connect your controller, then start.')
        ttk.Label(panel, textvariable=self.state, wraplength=570).pack(anchor='w', pady=(0, 12))
        actions = ttk.Frame(panel)
        actions.pack(fill='x')
        self.start_button = ttk.Button(actions, text='Start bridge', command=self.start)
        self.start_button.pack(side='left')
        self.stop_button = ttk.Button(actions, text='Stop', command=self.stop.set, state='disabled')
        self.stop_button.pack(side='left', padx=8)
        ttk.Button(actions, text='Diagnostics', command=self.diagnose).pack(side='right')
        ttk.Separator(panel).pack(fill='x', pady=16)
        ttk.Label(panel, text='Button mapping', font=('', 13, 'bold')).pack(anchor='w')
        ttk.Label(panel, text='Changes apply the next time you start the bridge.').pack(anchor='w', pady=(2, 8))
        grid = ttk.Frame(panel)
        grid.pack(fill='x')
        self.bindings = {}
        choices = ['Disabled', *BUTTONS]
        for i, name in enumerate(BUTTONS | EXTRAS):
            col, row = (i // 9)*2, i % 9
            ttk.Label(grid, text=name).grid(row=row, column=col, sticky='w', padx=(0, 8), pady=3)
            var = tk.StringVar(value=self.profile['bindings'].get(name, name if name in BUTTONS else 'Disabled'))
            self.bindings[name] = var
            ttk.Combobox(grid, values=choices, textvariable=var, state='readonly', width=10).grid(row=row, column=col+1, padx=(0, 22), pady=3)
        dzrow = ttk.Frame(panel)
        dzrow.pack(fill='x', pady=12)
        ttk.Label(dzrow, text='Stick deadzone (0–50%)').pack(side='left')
        self.deadzone = tk.StringVar(value=str(round(self.profile['deadzone']*100)))
        ttk.Spinbox(dzrow, from_=0, to=50, textvariable=self.deadzone, width=6).pack(side='left', padx=12)
        files = ttk.Frame(panel)
        files.pack(fill='x')
        ttk.Button(files, text='Load profile…', command=self.load).pack(side='left')
        ttk.Button(files, text='Save profile…', command=self.save).pack(side='left', padx=8)
        motion_panel = ttk.LabelFrame(panel, text='Motion and rumble', padding=8)
        motion_panel.pack(fill='x', pady=10)
        self.motion_vars = {}
        settings = self.profile['motion']
        rows = [('left_pad', 'Left trackpad', ('off', 'mouse', 'left-stick', 'right-stick', 'dpad')),
                ('right_pad', 'Right trackpad', ('off', 'mouse', 'left-stick', 'right-stick', 'dpad')),
                ('gyro', 'Gyro output', ('off', 'mouse', 'right-stick')),
                ('gyro_button', 'Hold to aim', ('Always', *BUTTONS, *EXTRAS))]
        for row, (key, label, choices) in enumerate(rows):
            ttk.Label(motion_panel, text=label).grid(row=row, column=0, sticky='w')
            var = tk.StringVar(value=settings[key])
            self.motion_vars[key] = var
            ttk.Combobox(motion_panel, textvariable=var, values=choices, state='readonly', width=16).grid(row=row, column=1, padx=8, pady=2)
        for row, (key, label, low, high, step) in enumerate([
                ('pad_sensitivity', 'Pad sensitivity', .001, 1, .005),
                ('gyro_sensitivity', 'Gyro sensitivity', .1, 100, 1),
                ('gyro_deadzone', 'Gyro deadzone °/s', 0, 20, .1)]):
            ttk.Label(motion_panel, text=label).grid(row=row, column=2, sticky='w')
            var = tk.StringVar(value=str(settings[key]))
            self.motion_vars[key] = var
            ttk.Spinbox(motion_panel, textvariable=var, from_=low, to=high, increment=step, width=7).grid(row=row, column=3, padx=5)
        for row, key, label in [(4, 'rumble', 'Enable game rumble'), (5, 'invert_gyro_y', 'Invert gyro Y')]:
            var = tk.BooleanVar(value=settings[key])
            self.motion_vars[key] = var
            ttk.Checkbutton(motion_panel, text=label, variable=var).grid(row=row, column=0, columnspan=2, sticky='w')
        ttk.Label(panel, text='Mouse pad mode: hold the pad click while sliding. Gyro needs a matching sensor;\nrumble needs driver support. Restart the bridge after changing settings.', wraplength=660).pack(anchor='w')
        self.log = tk.Text(panel, height=7, wrap='word', state='disabled')
        self.log.pack(fill='both', expand=True)
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(100, self.poll)

    def current(self):
        motion = dict(self.profile['motion'])
        for key, var in self.motion_vars.items():
            motion[key] = float(var.get()) if key in ('pad_sensitivity', 'gyro_sensitivity', 'gyro_deadzone') else var.get()
        return validate({'motion': motion, 'deadzone': float(self.deadzone.get())/100,
                         'bindings': {name: var.get() for name, var in self.bindings.items()}})

    def start(self):
        if self.worker and self.worker.is_alive():
            return
        try:
            profile = self.current()
        except ValueError as exc:
            messagebox.showerror('Invalid profile', str(exc))
            return
        self.stop.clear()
        def work():
            try:
                backend.run(self.stop, profile, self.messages.put)
            except Exception as exc:
                self.messages.put(f'Error: {exc}')
        self.worker = threading.Thread(target=work, daemon=False)
        self.worker.start()
        self.start_button.configure(state='disabled')
        self.stop_button.configure(state='normal')

    def poll(self):
        while not self.messages.empty():
            message = self.messages.get_nowait()
            self.state.set(message)
            self.log.configure(state='normal')
            self.log.insert('end', message+'\n')
            if int(self.log.index('end-1c').split('.')[0]) > 250:
                self.log.delete('1.0', '50.0')
            self.log.see('end')
            self.log.configure(state='disabled')
        active = bool(self.worker and self.worker.is_alive())
        if not active:
            self.start_button.configure(state='normal')
            self.stop_button.configure(state='disabled')
            if self.closing:
                self.root.destroy()
                return
        self.root.after(100, self.poll)

    def close(self):
        self.closing = True
        self.stop.set()
        self.state.set('Stopping and releasing controller…')

    def diagnose(self):
        try:
            messagebox.showinfo('Diagnostics', backend.diagnostics())
        except Exception as exc:
            messagebox.showerror('Diagnostics', str(exc))

    def load(self):
        path = filedialog.askopenfilename(filetypes=[('Profiles', '*.json')])
        if not path:
            return
        try:
            profile = load_profile(path)
            self.profile = profile
            for key, var in self.motion_vars.items():
                var.set(profile['motion'][key])
            self.deadzone.set(str(profile['deadzone']*100))
            for name, var in self.bindings.items():
                var.set(profile['bindings'].get(name, name if name in BUTTONS else 'Disabled'))
        except (OSError, ValueError) as exc:
            messagebox.showerror('Profile error', str(exc))

    def save(self):
        try:
            profile = self.current()
            path = filedialog.asksaveasfilename(defaultextension='.json', filetypes=[('Profiles', '*.json')])
            if path:
                target = Path(path)
                temporary = target.with_name(target.name+'.tmp')
                temporary.write_text(json.dumps(profile, indent=2)+'\n')
                temporary.replace(target)
        except (OSError, ValueError) as exc:
            messagebox.showerror('Profile error', str(exc))

def launch(profile_path=None):
    root = tk.Tk()
    Window(root, profile_path)
    root.mainloop()
