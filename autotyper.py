import time
import random
import threading
import ctypes
from ctypes import wintypes
import customtkinter as ctk

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

user32 = ctypes.WinDLL('user32', use_last_error=True)

ULONG_PTR = wintypes.WPARAM
INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

VK_LBUTTON = 0x01
VK_BACK = 0x08
VK_TAB = 0x09
VK_RETURN = 0x0D
VK_SHIFT = 0x10
VK_ESCAPE = 0x1B
VK_SPACE = 0x20
VK_END = 0x23
VK_HOME = 0x24
VK_LEFT = 0x25
VK_DELETE = 0x2E


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUTunion(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("union", _INPUTunion),
    ]


class GUITHREADINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hwndActive", wintypes.HWND),
        ("hwndFocus", wintypes.HWND),
        ("hwndCapture", wintypes.HWND),
        ("hwndMenuOwner", wintypes.HWND),
        ("hwndMoveSize", wintypes.HWND),
        ("hwndCaret", wintypes.HWND),
        ("rcCaret", wintypes.RECT),
    ]


user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT
user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
user32.GetAsyncKeyState.restype = wintypes.SHORT
user32.SendMessageTimeoutW.argtypes = (
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
    wintypes.UINT,
    wintypes.UINT,
    ctypes.POINTER(ULONG_PTR),
)
user32.SendMessageTimeoutW.restype = wintypes.LPARAM


def is_key_pressed(vk):
    return (user32.GetAsyncKeyState(vk) & 0x8000) != 0


def _make_vk_input(vk, flags=0):
    scan = user32.MapVirtualKeyW(vk, 0)
    ki = KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=0)
    return INPUT(type=INPUT_KEYBOARD, union=_INPUTunion(ki=ki))


def _make_unicode_input(code_unit, flags=0):
    ki = KEYBDINPUT(
        wVk=0,
        wScan=code_unit,
        dwFlags=KEYEVENTF_UNICODE | flags,
        time=0,
        dwExtraInfo=0,
    )
    return INPUT(type=INPUT_KEYBOARD, union=_INPUTunion(ki=ki))


def send_inputs(*inputs):
    n = len(inputs)
    if n == 0:
        return
    arr = (INPUT * n)(*inputs)
    cb_size = ctypes.sizeof(INPUT)
    sent = 0
    while sent < n:
        ptr = ctypes.cast(
            ctypes.byref(arr, sent * cb_size), ctypes.POINTER(INPUT)
        )
        res = user32.SendInput(n - sent, ptr, cb_size)
        if res > 0:
            sent += res
        else:
            time.sleep(0.002)


def tap_vk(vk, extended=False, with_shift=False):
    ext_flag = KEYEVENTF_EXTENDEDKEY if extended else 0
    events = []
    if with_shift:
        events.append(_make_vk_input(VK_SHIFT, 0))
    events.append(_make_vk_input(vk, ext_flag))
    events.append(_make_vk_input(vk, ext_flag | KEYEVENTF_KEYUP))
    if with_shift:
        events.append(_make_vk_input(VK_SHIFT, KEYEVENTF_KEYUP))
    send_inputs(*events)


def send_unicode_char(ch):
    utf16 = ch.encode("utf-16-le")
    units = [
        int.from_bytes(utf16[i : i + 2], "little")
        for i in range(0, len(utf16), 2)
    ]
    events = []
    for u in units:
        events.append(_make_unicode_input(u, 0))
        events.append(_make_unicode_input(u, KEYEVENTF_KEYUP))
    send_inputs(*events)


def get_target_hwnd():
    hwnd = user32.GetForegroundWindow()
    if hwnd:
        tid = user32.GetWindowThreadProcessId(hwnd, None)
        gti = GUITHREADINFO(cbSize=ctypes.sizeof(GUITHREADINFO))
        if user32.GetGUIThreadInfo(tid, ctypes.byref(gti)) and gti.hwndFocus:
            return gti.hwndFocus
    return hwnd


def sync_target_window(hwnd=None, timeout_ms=250):
    target = hwnd or get_target_hwnd()
    if target:
        result = ULONG_PTR(0)
        SMTO_NORMAL = 0x0000
        WM_NULL = 0x0000
        user32.SendMessageTimeoutW(
            target,
            WM_NULL,
            0,
            0,
            SMTO_NORMAL,
            timeout_ms,
            ctypes.byref(result),
        )


class AutoTyperApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("AutoTyper")
        self.geometry("840x650")
        self.minsize(680, 520)

        self.stop_event = threading.Event()
        self.is_running = False
        self.current_text = ""
        self.current_base_delay = 0.005
        self.current_humanize = True
        self.current_ide_mode = True
        self.current_minimize = True

        self._build_ui()
        self._setup_bindings()

        self.esc_monitor_thread = threading.Thread(
            target=self._esc_monitor_loop, daemon=True
        )
        self.esc_monitor_thread.start()

    def _build_ui(self):
        top_frame = ctk.CTkFrame(self, fg_color="transparent")
        top_frame.pack(fill="x", padx=20, pady=(15, 5))

        self.status_label = ctk.CTkLabel(
            top_frame,
            text="🟢 Готов к работе",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#4ADE80",
        )
        self.status_label.pack(side="left")

        self.stats_label = ctk.CTkLabel(
            top_frame,
            text="Строк: 0 | Символов: 0",
            font=ctk.CTkFont(size=12),
            text_color="gray",
        )
        self.stats_label.pack(side="right")

        self.textbox = ctk.CTkTextbox(
            self,
            font=ctk.CTkFont(family="Consolas", size=13),
            wrap="none",
            undo=True,
            corner_radius=8,
            border_width=1,
            border_color="#333333",
        )
        self.textbox.pack(fill="both", expand=True, padx=20, pady=10)
        self.textbox._textbox.configure(tabs=("1c", "2c", "3c", "4c"))

        clip_frame = ctk.CTkFrame(self, fg_color="transparent")
        clip_frame.pack(fill="x", padx=20, pady=(0, 10))

        ctk.CTkButton(
            clip_frame,
            text="📥 Вставить из буфера",
            width=160,
            height=32,
            fg_color="#2B2B2B",
            hover_color="#3A3A3A",
            command=self.paste_from_clipboard,
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            clip_frame,
            text="📋 Скопировать в буфер",
            width=170,
            height=32,
            fg_color="#2B2B2B",
            hover_color="#3A3A3A",
            command=self.copy_to_clipboard,
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            clip_frame,
            text="🗑 Очистить",
            width=110,
            height=32,
            fg_color="#3A1D1D",
            hover_color="#522727",
            text_color="#F87171",
            command=self.clear_text,
        ).pack(side="right")

        settings_frame = ctk.CTkFrame(self, corner_radius=8)
        settings_frame.pack(fill="x", padx=20, pady=(0, 15))

        speed_top = ctk.CTkFrame(settings_frame, fg_color="transparent")
        speed_top.pack(fill="x", padx=15, pady=(12, 2))

        ctk.CTkLabel(
            speed_top,
            text="Скорость печати (задержка между символами):",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(side="left")

        self.speed_value_label = ctk.CTkLabel(
            speed_top,
            text="5 мс (~200 симв/сек — Быстро)",
            font=ctk.CTkFont(size=13),
            text_color="#60A5FA",
        )
        self.speed_value_label.pack(side="right")

        self.speed_slider = ctk.CTkSlider(
            settings_frame,
            from_=1,
            to=120,
            number_of_steps=119,
            command=self._update_speed_label,
        )
        self.speed_slider.set(5)
        self.speed_slider.pack(fill="x", padx=15, pady=(5, 12))

        opts_frame = ctk.CTkFrame(settings_frame, fg_color="transparent")
        opts_frame.pack(fill="x", padx=15, pady=(0, 12))

        self.humanize_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            opts_frame,
            text="Имитация человека (случайный ритм)",
            variable=self.humanize_var,
            font=ctk.CTkFont(size=12),
        ).pack(side="left", padx=(0, 20))

        self.ide_mode_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            opts_frame,
            text="Режим кода (PyCharm / VS Code / Веб-IDE)",
            variable=self.ide_mode_var,
            font=ctk.CTkFont(size=12),
        ).pack(side="left", padx=(0, 20))

        self.minimize_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            opts_frame,
            text="Сворачивать окно",
            variable=self.minimize_var,
            font=ctk.CTkFont(size=12),
        ).pack(side="left")

        action_frame = ctk.CTkFrame(self, fg_color="transparent")
        action_frame.pack(fill="x", padx=20, pady=(0, 20))

        self.start_btn = ctk.CTkButton(
            action_frame,
            text="🎯 Выбрать место и напечатать",
            font=ctk.CTkFont(size=15, weight="bold"),
            height=45,
            fg_color="#2563EB",
            hover_color="#1D4ED8",
            command=self.start_selection_mode,
        )
        self.start_btn.pack(side="left", fill="x", expand=True, padx=(0, 10))

        self.stop_btn = ctk.CTkButton(
            action_frame,
            text="⏹ Стоп (ESC)",
            font=ctk.CTkFont(size=14, weight="bold"),
            width=140,
            height=45,
            fg_color="#DC2626",
            hover_color="#B91C1C",
            state="disabled",
            command=self.stop_process,
        )
        self.stop_btn.pack(side="right")

    def _setup_bindings(self):
        self.textbox.bind("<KeyRelease>", self._update_stats)
        self.textbox.bind("<Control-KeyPress>", self._handle_russian_shortcuts)

    def _handle_russian_shortcuts(self, event):
        if event.keycode == 86 and event.keysym.lower() != "v":
            self.paste_from_clipboard()
            return "break"
        elif event.keycode == 67 and event.keysym.lower() != "c":
            self.copy_to_clipboard()
            return "break"
        elif event.keycode == 65 and event.keysym.lower() != "a":
            self.textbox.tag_add("sel", "1.0", "end")
            return "break"

    def _update_stats(self, event=None):
        text = self.textbox.get("1.0", "end-1c")
        if not text:
            self.stats_label.configure(text="Строк: 0 | Символов: 0")
            return
        lines = text.count("\n") + 1
        chars = len(text)
        self.stats_label.configure(text=f"Строк: {lines} | Символов: {chars}")

    def _update_speed_label(self, value):
        ms = int(value)
        cps = int(1000 / ms) if ms > 0 else 1000
        if ms <= 3:
            desc = "Турбо"
        elif ms <= 15:
            desc = "Быстро"
        elif ms <= 50:
            desc = "Средне"
        else:
            desc = "Медленно"
        self.speed_value_label.configure(text=f"{ms} мс (~{cps} симв/сек — {desc})")

    def paste_from_clipboard(self):
        try:
            clip_text = self.clipboard_get()
            clip_text = clip_text.replace("\r\n", "\n").replace("\r", "\n")
            try:
                sel_start = self.textbox.index("sel.first")
                sel_end = self.textbox.index("sel.last")
                self.textbox.delete(sel_start, sel_end)
                self.textbox.insert(sel_start, clip_text)
            except Exception:
                self.textbox.insert("insert", clip_text)
            self._update_stats()
            self._set_status("📥 Текст вставлен из буфера обмена", "#60A5FA")
        except Exception:
            self._set_status("⚠️ Буфер обмена пуст или не содержит текст", "#FBBF24")

    def copy_to_clipboard(self):
        text = self.textbox.get("1.0", "end-1c")
        if not text:
            self._set_status("⚠️ Нет текста для копирования", "#FBBF24")
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()
        self._set_status("📋 Результат скопирован в буфер обмена!", "#4ADE80")

    def clear_text(self):
        self.textbox.delete("1.0", "end")
        self._update_stats()
        self._set_status("🗑 Поле очищено", "gray")

    def _set_status(self, text, color="#4ADE80"):
        self.status_label.configure(text=text, text_color=color)

    def _esc_monitor_loop(self):
        was_esc = False
        while True:
            is_esc = is_key_pressed(VK_ESCAPE)
            if is_esc and not was_esc and self.is_running:
                self.stop_event.set()
                self.after(0, self.stop_process)
            was_esc = is_esc
            time.sleep(0.015)

    def start_selection_mode(self):
        text = self.textbox.get("1.0", "end-1c")
        if not text:
            self._set_status("⚠️ Сначала вставьте или введите текст!", "#F87171")
            return

        self.current_text = text.replace("\r\n", "\n").replace("\r", "\n")
        self.current_base_delay = self.speed_slider.get() / 1000.0
        self.current_humanize = self.humanize_var.get()
        self.current_ide_mode = self.ide_mode_var.get()
        self.current_minimize = self.minimize_var.get()

        self.is_running = True
        self.stop_event.clear()

        self.start_btn.configure(state="disabled", text="⏳ Кликните в нужное место...")
        self.stop_btn.configure(state="normal")
        self._set_status(
            "🎯 Кликните ЛКМ в поле, куда нужно ввести текст (ESC — отмена)", "#FBBF24"
        )

        if self.current_minimize:
            self.iconify()

        threading.Thread(target=self._wait_for_click_and_type, daemon=True).start()

    def _wait_for_click_and_type(self):
        while is_key_pressed(VK_LBUTTON):
            if self.stop_event.is_set() or not self.is_running:
                return
            time.sleep(0.01)

        time.sleep(0.15)

        while not self.stop_event.is_set() and self.is_running:
            if is_key_pressed(VK_LBUTTON):
                while is_key_pressed(VK_LBUTTON):
                    if self.stop_event.is_set() or not self.is_running:
                        return
                    time.sleep(0.01)

                if not self.stop_event.is_set() and self.is_running:
                    self._type_text_worker()
                return
            time.sleep(0.01)

    def _clear_ide_end_of_line_artifacts(self, target_hwnd=None):
        sync_target_window(target_hwnd, 150)
        tap_vk(VK_SPACE)
        time.sleep(0.01)
        tap_vk(VK_LEFT, extended=True, with_shift=False)
        time.sleep(0.01)
        tap_vk(VK_END, extended=True, with_shift=True)
        time.sleep(0.01)
        tap_vk(VK_DELETE, extended=True, with_shift=False)
        time.sleep(0.01)
        sync_target_window(target_hwnd, 150)

    def _reset_ide_line_indent(self, target_hwnd=None):
        sync_target_window(target_hwnd, 150)
        time.sleep(0.025)
        send_unicode_char("_")
        time.sleep(0.012)
        tap_vk(VK_HOME, extended=True, with_shift=True)
        time.sleep(0.012)
        tap_vk(VK_HOME, extended=True, with_shift=True)
        time.sleep(0.012)
        tap_vk(VK_DELETE, extended=True, with_shift=False)
        time.sleep(0.015)
        sync_target_window(target_hwnd, 150)

    def _type_text_worker(self):
        time.sleep(0.25)
        if self.stop_event.is_set():
            return

        self.after(
            0,
            lambda: self._set_status(
                "⌨️ Печатаю текст... (Нажмите ESC для остановки)", "#60A5FA"
            ),
        )

        lines = self.current_text.split("\n")
        base_delay = self.current_base_delay
        humanize = self.current_humanize
        ide_mode = self.current_ide_mode
        minimize = self.current_minimize
        target_hwnd = get_target_hwnd()

        try:
            ctypes.windll.winmm.timeBeginPeriod(1)
        except Exception:
            pass

        try:
            total_lines = len(lines)
            chars_since_sync = 0

            for line_idx, line in enumerate(lines):
                if self.stop_event.is_set():
                    break

                for char in line:
                    if self.stop_event.is_set():
                        break

                    if char == "\t":
                        tap_vk(VK_TAB)
                    else:
                        send_unicode_char(char)

                    chars_since_sync += 1

                    delay = base_delay
                    if humanize:
                        delay *= random.uniform(0.5, 1.6)
                        if char in (".", ",", ";", ":", ")"):
                            delay += random.uniform(0.01, 0.03)

                    time.sleep(delay)

                    if base_delay <= 0.005 and chars_since_sync >= 25:
                        sync_target_window(target_hwnd, 100)
                        chars_since_sync = 0

                if self.stop_event.is_set():
                    break

                if line_idx < total_lines - 1:
                    if ide_mode and any(c in line for c in "([{\"'"):
                        self._clear_ide_end_of_line_artifacts(target_hwnd)

                    tap_vk(VK_RETURN)
                    chars_since_sync = 0

                    if ide_mode:
                        self._reset_ide_line_indent(target_hwnd)
                    else:
                        if base_delay <= 0.005:
                            sync_target_window(target_hwnd, 100)
                        time.sleep(max(base_delay, 0.005))

            if not self.stop_event.is_set():
                sync_target_window(target_hwnd, 2000)
                if minimize:
                    self.after(
                        0,
                        lambda: self._set_status(
                            "⏳ Завершение ввода (ожидание 2 сек перед открытием окна)...",
                            "#FBBF24",
                        ),
                    )
                    for _ in range(40):
                        if self.stop_event.is_set():
                            break
                        time.sleep(0.05)
                else:
                    time.sleep(0.15)
                sync_target_window(target_hwnd, 2000)

        finally:
            try:
                ctypes.windll.winmm.timeEndPeriod(1)
            except Exception:
                pass

        if not self.stop_event.is_set():
            self.after(0, self._on_typing_complete)

    def _on_typing_complete(self):
        self.is_running = False
        self.start_btn.configure(state="normal", text="🎯 Выбрать место и напечатать")
        self.stop_btn.configure(state="disabled")
        self._set_status("✅ Ввод текста успешно завершён!", "#4ADE80")
        if self.current_minimize:
            self.deiconify()

    def stop_process(self):
        self.stop_event.set()
        self.is_running = False
        self.start_btn.configure(state="normal", text="🎯 Выбрать место и напечатать")
        self.stop_btn.configure(state="disabled")
        self._set_status("🛑 Остановлено пользователем", "#F87171")
        if self.state() == "iconic":
            self.deiconify()


if __name__ == "__main__":
    app = AutoTyperApp()
    app.mainloop()