import os
import re
import subprocess
import sys
import threading

# macOS: UV 管理的 Python 内置 Tcl/Tk 但路径不对
# 引导 _tkinter 找到正确的 init.tcl / tk.tcl
if sys.platform == "darwin" and "TCL_LIBRARY" not in os.environ:
    _pyroot = os.path.dirname(os.path.dirname(os.path.realpath(sys.executable)))
    for _lib, _sub in [("TCL_LIBRARY", "tcl8.6"), ("TK_LIBRARY", "tk8.6")]:
        _p = os.path.join(_pyroot, "lib", _sub)
        if os.path.isdir(_p):
            os.environ[_lib] = _p

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path


def _load_env(env_path: str = ".env") -> dict:
    extra = {}
    if not os.path.exists(env_path):
        return extra
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            extra[k.strip()] = v.strip()
    return extra


def _configured_secret(value: str | None) -> bool:
    if not value:
        return False
    value = value.strip()
    if not value:
        return False
    placeholders = ("你的", "your_", "your-", "sk-...", "hf_...")
    return not any(marker in value.lower() for marker in placeholders)


STEPS = [
    (r"步骤1/6", "提取音频"),
    (r"步骤2/6", "语音转文字"),
    (r"步骤3/6", "说话人分离"),
    (r"步骤4/6|检测到.*QA", "分析问答对"),
    (r"步骤5/6", "生成标题"),
    (r"步骤6/6", "切片输出"),
    (r"完成！", "完成"),
    (r"❌", "出错"),
]


def _estimate_progress(line: str, current: int) -> int:
    for i, (pattern, _) in enumerate(STEPS):
        if re.search(pattern, line):
            return int((i + 1) / len(STEPS) * 100)
    return current


class CastFluxGUI:
    def __init__(self):
        self.window = tk.Tk()
        self.window.title("CastFlux 直播切片工具")
        self.window.geometry("860x680")
        self.window.minsize(720, 540)

        self.video_path = tk.StringVar()
        self.output_dir = tk.StringVar(value="output_slices")
        self.model = tk.StringVar(value="tiny")
        self.num_slices = tk.IntVar(value=4)
        self.speed = tk.DoubleVar(value=1.3)

        self.running = False
        self.process = None
        self.cancelled = False
        self.progress_val = 0

        self._build_ui()
        self.window.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        self.window.columnconfigure(0, weight=1)
        self.window.rowconfigure(3, weight=1)

        style = ttk.Style()
        style.theme_use("clam")

        # ------ 标题 ------
        title = tk.Label(self.window, text="CastFlux 直播切片工具",
                         font=("Helvetica", 18, "bold"), fg="#2d3436")
        title.grid(row=0, column=0, pady=(16, 4))

        sub = tk.Label(self.window, text="自动提取问答片段 → 加速出片",
                       font=("Helvetica", 11), fg="#636e72")
        sub.grid(row=1, column=0, pady=(0, 12))

        # ------ 主面板 ------
        main = ttk.Frame(self.window, padding=12)
        main.grid(row=2, column=0, sticky="ew")
        main.columnconfigure(1, weight=1)

        row = 0
        ttk.Label(main, text="输入视频:").grid(row=row, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(main, textvariable=self.video_path).grid(row=row, column=1, sticky="ew")
        ttk.Button(main, text="浏览…", command=self._browse_video, width=8
                   ).grid(row=row, column=2, padx=(6, 0))
        row += 1

        ttk.Label(main, text="输出目录:").grid(row=row, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(main, textvariable=self.output_dir).grid(row=row, column=1, sticky="ew")
        ttk.Button(main, text="浏览…", command=self._browse_output, width=8
                   ).grid(row=row, column=2, padx=(6, 0))
        row += 1

        # 参数行
        pf = ttk.Frame(main)
        pf.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        pf.columnconfigure((1, 3, 5), weight=1)

        ttk.Label(pf, text="模型:").grid(row=0, column=0, padx=(0, 4))
        self.model_combo = ttk.Combobox(pf, textvariable=self.model,
                                        values=["tiny", "base", "small", "medium", "large-v3"],
                                        width=10, state="readonly")
        self.model_combo.grid(row=0, column=1, padx=(0, 20), sticky="w")

        ttk.Label(pf, text="切片数:").grid(row=0, column=2, padx=(0, 4))
        ttk.Spinbox(pf, from_=1, to=20, textvariable=self.num_slices,
                    width=6).grid(row=0, column=3, padx=(0, 20), sticky="w")

        ttk.Label(pf, text="倍速:").grid(row=0, column=4, padx=(0, 4))
        ttk.Spinbox(pf, from_=1.0, to=2.0, increment=0.1,
                    textvariable=self.speed, width=6).grid(row=0, column=5, sticky="w")

        # ------ 操作按钮 ------
        btn_frame = ttk.Frame(self.window, padding=12)
        btn_frame.grid(row=3, column=0, sticky="ew")
        btn_frame.columnconfigure(0, weight=1)
        btn_frame.columnconfigure(1, weight=1)

        self.start_btn = ttk.Button(btn_frame, text="▶ 开始切片",
                                    command=self._start_slicing)
        self.start_btn.grid(row=0, column=0, padx=(0, 6), sticky="ew")

        self.cancel_btn = ttk.Button(btn_frame, text="■ 取消",
                                     command=self._cancel, state="disabled")
        self.cancel_btn.grid(row=0, column=1, padx=(6, 0), sticky="ew")

        # ------ 日志 + 进度 ------
        log_frame = ttk.LabelFrame(self.window, text="运行日志", padding=6)
        log_frame.grid(row=4, column=0, sticky="nsew", padx=12, pady=(0, 8))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = tk.Text(log_frame, height=14, wrap="word",
                                font=("Menlo", 10), bg="#1e1e1e", fg="#d4d4d4",
                                insertbackground="white", state="disabled",
                                relief="flat", borderwidth=0)
        self.log_text.grid(row=0, column=0, sticky="nsew")

        scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scroll.set)

        # 进度条
        prog_frame = ttk.Frame(self.window, padding=(12, 0, 12, 12))
        prog_frame.grid(row=5, column=0, sticky="ew")
        prog_frame.columnconfigure(1, weight=1)

        self.prog_label = ttk.Label(prog_frame, text="就绪")
        self.prog_label.grid(row=0, column=0, padx=(0, 8))

        self.prog_bar = ttk.Progressbar(prog_frame, mode="determinate", value=0)
        self.prog_bar.grid(row=0, column=1, sticky="ew")

        # ------ 设置 / 帮助 ------
        bottom = ttk.Frame(self.window)
        bottom.grid(row=6, column=0, sticky="ew", padx=12, pady=(0, 12))
        ttk.Button(bottom, text="⚙ 设置 API Key", command=self._settings_dialog
                   ).pack(side="left")
        ttk.Label(bottom, text="").pack(side="left", fill="x", expand=True)
        ttk.Label(bottom, text="v1.0", foreground="#b2bec3"
                  ).pack(side="right")

    # ---------- helpers ----------

    def _browse_video(self):
        path = filedialog.askopenfilename(
            title="选择视频文件",
            filetypes=[("视频文件", "*.mp4 *.avi *.mov *.mkv"), ("所有文件", "*.*")],
        )
        if path:
            self.video_path.set(path)

    def _browse_output(self):
        path = filedialog.askdirectory(title="选择输出目录")
        if path:
            self.output_dir.set(path)

    def _log(self, msg: str):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _set_progress(self, val: int, text: str = None):
        self.progress_val = val
        self.prog_bar["value"] = val
        if text:
            self.prog_label["text"] = text
        self.window.update_idletasks()

    def _set_busy(self, busy: bool):
        state = "disabled" if busy else "normal"
        self.start_btn.configure(state=state)
        self.cancel_btn.configure(state="normal" if busy else "disabled")
        self.model_combo.configure(state="disabled" if busy else "readonly")
        self.running = busy
        self.window.update_idletasks()

    def _on_close(self):
        if self.running:
            if not messagebox.askyesno("确认退出", "正在处理中，确定要退出吗？"):
                return
            self._cancel()
        self.window.destroy()

    def _cancel(self):
        self.cancelled = True
        if self.process:
            try:
                self.process.terminate()
            except Exception:
                pass
        self._log("⏹ 用户取消")
        self._set_progress(0, "已取消")
        self._set_busy(False)

    # ---------- settings ----------

    def _read_env(self):
        env = {}
        for p in [".env", os.path.expanduser("~/.env")]:
            env.update(_load_env(p))
        return env

    def _settings_dialog(self):
        env = self._read_env()
        win = tk.Toplevel(self.window)
        win.title("API Key 设置")
        win.geometry("520x360")
        win.resizable(False, False)
        win.transient(self.window)
        win.grab_set()

        keys = [
            ("HF_TOKEN", "HuggingFace Token（必需）",
             "用于下载说话人分离模型"),
            ("DEEPSEEK_API_KEY", "DeepSeek API Key（默认）",
             "如用其他 LLM 可以不填"),
            ("QWEN_API_KEY", "通义千问 Qwen Key（可选）", ""),
            ("GLM_API_KEY", "智谱 GLM Key（可选）", ""),
            ("MINIMAX_API_KEY", "MiniMax Key（可选）", ""),
            ("OPENAI_API_KEY", "OpenAI Key（可选）", ""),
        ]
        vars_ = {}
        for i, (key, label, hint) in enumerate(keys):
            ttk.Label(win, text=label).grid(row=i, column=0, sticky="w",
                                            padx=12, pady=(12 if i == 0 else 4, 0))
            v = tk.StringVar(value=env.get(key, ""))
            vars_[key] = v
            e = ttk.Entry(win, textvariable=v, width=60, show="*" if "TOKEN" in key or "KEY" in key else "")
            e.grid(row=i, column=0, columnspan=2, padx=12, pady=(0, 2), sticky="ew")
            if hint:
                ttk.Label(win, text=hint, foreground="#636e72",
                          font=("", 9)).grid(row=i, column=0, columnspan=2,
                                             padx=12, pady=(0, 6), sticky="w")

        def save():
            lines = []
            for key, var in vars_.items():
                val = var.get().strip()
                if val:
                    lines.append(f"{key}={val}")
            try:
                with open(".env", "w", encoding="utf-8") as f:
                    f.write("\n".join(lines) + "\n")
                messagebox.showinfo("保存成功", "API Key 已保存到 .env 文件", parent=win)
                win.destroy()
            except Exception as e:
                messagebox.showerror("保存失败", str(e), parent=win)

        ttk.Button(win, text="保存", command=save
                   ).grid(row=len(keys) + 1, column=0, pady=16)
        ttk.Button(win, text="取消", command=win.destroy
                   ).grid(row=len(keys) + 1, column=1, pady=16, padx=(6, 12))

    # ---------- pipeline ----------

    def _build_env(self) -> dict:
        env = os.environ.copy()
        env.update(_load_env(".env"))
        local_ffmpeg = str(Path(__file__).resolve().parent.parent.parent
                           / "scripts" / "ffmpeg" / "bin")
        if os.path.isdir(local_ffmpeg) and local_ffmpeg not in env.get("PATH", ""):
            env["PATH"] = f"{local_ffmpeg};{env.get('PATH', '')}"
        return env

    def _find_ffmpeg(self) -> str | None:
        """找 ffmpeg：PATH → 项目自带 scripts/ffmpeg/bin → None"""
        for name in ("ffmpeg", "ffmpeg.exe"):
            try:
                subprocess.run([name, "-version"], capture_output=True, check=True)
                return name
            except (subprocess.CalledProcessError, FileNotFoundError):
                pass
        local = str(Path(__file__).resolve().parent.parent.parent
                    / "scripts" / "ffmpeg" / "bin" / "ffmpeg.exe")
        if os.path.exists(local):
            return local
        return None

    def _check_ffmpeg(self) -> bool:
        return self._find_ffmpeg() is not None

    def _start_slicing(self):
        if not self.video_path.get():
            messagebox.showwarning("提示", "请先选择视频文件")
            return
        if not os.path.exists(self.video_path.get()):
            messagebox.showerror("错误", "视频文件不存在")
            return

        if not self._check_ffmpeg():
            ret = messagebox.askyesno(
                "缺少 ffmpeg",
                "未检测到 ffmpeg，无法处理视频。\n"
                "是否打开下载页面？（Windows 用户推荐下载 FFmpeg）\n"
                "下载后请将 ffmpeg.exe 所在目录添加到系统 PATH。",
            )
            if ret:
                import webbrowser
                webbrowser.open("https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip")
            return

        env = self._build_env()
        if not _configured_secret(env.get("HF_TOKEN")):
            ret = messagebox.askyesno(
                "缺少 HF_TOKEN",
                "未设置 HuggingFace Token，说话人分离将无法工作。\n"
                "是否现在设置 API Key？",
            )
            if ret:
                self._settings_dialog()
            return

        if not (
            _configured_secret(env.get("DEEPSEEK_API_KEY"))
            or _configured_secret(env.get("QWEN_API_KEY"))
            or _configured_secret(env.get("GLM_API_KEY"))
            or _configured_secret(env.get("MINIMAX_API_KEY"))
            or _configured_secret(env.get("OPENAI_API_KEY"))
        ):
            ret = messagebox.askyesno(
                "缺少 API Key",
                "未设置 DeepSeek/Qwen/GLM/MiniMax/OpenAI API Key，无法生成标题和前情提要。\n"
                "是否现在设置 API Key？",
            )
            if ret:
                self._settings_dialog()
            return

        self._set_busy(True)
        self.cancelled = False
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        self._set_progress(0, "启动中…")
        self._log("=" * 50)
        self._log("CastFlux 启动")

        thread = threading.Thread(target=self._run, daemon=True)
        thread.start()

    def _run(self):
        video = self.video_path.get()
        output = self.output_dir.get()
        env = self._build_env()

        cmd = [
            sys.executable, "-m", "castflux",
            video,
            "-o", output,
            "--model", self.model.get(),
            "--num-slices", str(self.num_slices.get()),
            "--speed", str(self.speed.get()),
            "--verbose",
        ]

        self._log(f"命令: {' '.join(cmd)}")
        self._log("")

        try:
            self.process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, encoding="utf-8", errors="replace",
                env=env,
            )
        except Exception as e:
            self._log(f"❌ 启动失败: {e}")
            self._set_progress(0, "启动失败")
            self._set_busy(False)
            return

        progress = 0
        for line in self.process.stdout:
            if self.cancelled:
                break
            line = line.rstrip("\n\r")
            if line:
                self._log(line)
            progress = _estimate_progress(line, progress)
            self._set_progress(progress)

        self.process.wait()
        rc = self.process.returncode
        self.process = None

        if self.cancelled:
            pass
        elif rc == 0:
            self._log("")
            self._log("✅ 处理完成！")
            self._set_progress(100, "完成")
            messagebox.showinfo("完成", f"切片已保存到:\n{os.path.abspath(output)}")
        else:
            self._log("")
            self._log(f"❌ 处理失败 (返回码 {rc})，请检查日志")
            self._set_progress(0, "失败")

        self._set_busy(False)


def main():
    gui = CastFluxGUI()
    gui.window.mainloop()


if __name__ == "__main__":
    main()
