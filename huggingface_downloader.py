import tkinter as tk
from tkinter import filedialog, ttk, messagebox, font
import os
import threading
import time
import re
from datetime import datetime
import urllib3
import webbrowser
from huggingface_hub import snapshot_download, list_repo_files
from huggingface_hub.utils import HfHubHTTPError

# 增加格式化文件大小的辅助方法
def format_size(bytes, suffix="B"):
    """将字节数转换为人类可读的格式"""
    for unit in ["", "K", "M", "G", "T", "P", "E", "Z"]:
        if abs(bytes) < 1024.0:
            return f"{bytes:.2f} {unit}{suffix}"
        bytes /= 1024.0
    return f"{bytes:.2f} Y{suffix}"

class DownloadTracker:
    """跟踪下载进度和统计信息的类"""
    def __init__(self, gui):
        self.gui = gui
        self.total_files = 0
        self.downloaded_files = 0
        self.failed_files = []
        self.failed_files_info = {}  # 文件 -> 错误信息
        self.download_start_time = None
        self.download_end_time = None
        self.pulse_progress_interval = 200  # 进度条脉冲间隔(ms)，调整为更平滑
        self.total_bytes = 0
        self.last_update_time = time.time()
        
    def start(self):
        """开始下载跟踪"""
        self.total_files = 0
        self.downloaded_files = 0
        self.failed_files = []
        self.failed_files_info = {}
        self.download_start_time = datetime.now()
        self.total_bytes = 0
        self.last_update_time = time.time()
        
        # 启动进度条脉冲动画
        self.gui.progress_bar.config(mode='indeterminate')
        self.gui.progress_bar.start(self.pulse_progress_interval)
        self.gui.status_var.set("正在准备下载...")
    
    def end(self):
        """结束下载跟踪"""
        self.download_end_time = datetime.now()
        # 停止进度条动画
        self.gui.progress_bar.stop()
        self.gui.progress_bar.config(mode='determinate')
    
    def set_total_files(self, count):
        """设置预期的总文件数"""
        self.total_files = count
        self.gui.log(f"仓库中共有 {count} 个文件")
    
    def add_failed_file(self, filename, error_message):
        """记录失败的文件"""
        self.failed_files.append(filename)
        self.failed_files_info[filename] = error_message
        self.gui.log(f"文件下载失败: {os.path.basename(filename)}")
        self.gui.log(f"  错误: {error_message}")
    
    def get_summary(self):
        """生成下载任务的摘要信息"""
        # 计算下载时间
        if self.download_start_time and self.download_end_time:
            duration = (self.download_end_time - self.download_start_time).total_seconds()
            duration_str = f"{duration:.1f} 秒"
            if duration > 60:
                minutes = int(duration // 60)
                seconds = int(duration % 60)
                duration_str = f"{minutes} 分 {seconds} 秒"
        else:
            duration_str = "未知"
        
        # 从total_files中减去失败文件数来估算成功下载的文件数
        if self.total_files > 0:
            estimated_success = max(0, self.total_files - len(self.failed_files))
        else:
            estimated_success = "未知"
        
        # 构建摘要信息
        summary = [
            "======= 下载任务摘要 =======",
            f"总文件数: {self.total_files if self.total_files > 0 else '未知'}",
            f"成功下载: {estimated_success}",
            f"失败文件: {len(self.failed_files)}",
            f"下载用时: {duration_str}"
        ]
        
        # 如果有失败的文件，添加失败详情
        if self.failed_files:
            summary.append("\n==== 下载失败的文件 ====")
            for i, filename in enumerate(self.failed_files, 1):
                error_msg = self.failed_files_info.get(filename, "未知错误")
                summary.append(f"{i}. {os.path.basename(filename)}")
                summary.append(f"   错误: {error_msg}")
        
        # 根据失败类型提供建议
        if self.failed_files:
            summary.append("\n==== 故障排除建议 ====")
            
            # 分析错误类型
            network_errors = any("timeout" in str(err).lower() or 
                               "connection" in str(err).lower() or 
                               "incompleteread" in str(err).lower()
                               for err in self.failed_files_info.values())
            
            not_found_errors = any("not found" in str(err).lower() or 
                                 "404" in str(err).lower() 
                                 for err in self.failed_files_info.values())
            
            auth_errors = any("unauthorized" in str(err).lower() or 
                            "authentication" in str(err).lower() 
                            for err in self.failed_files_info.values())
            
            if network_errors:
                summary.append("• 网络连接问题:")
                summary.append("  - 检查您的网络连接是否稳定。")
                summary.append("  - 尝试更换代理服务器或检查代理设置。")
                summary.append("  - 确保已开启 断点续传 选项后重试。")
            
            if not_found_errors:
                summary.append("• 文件不存在问题:")
                summary.append("  - 确认仓库ID是否正确无误。")
                summary.append("  - 文件可能已被移除、重命名，或在特定分支/版本中不存在。")
                summary.append("  - 访问仓库页面检查最新文件列表。")
            
            if auth_errors:
                summary.append("• 认证问题:")
                summary.append("  - 如果是私有仓库，请确保您已在HuggingFace Hub登录或提供了有效的Token。")
                summary.append("  - 检查Token是否具有读取此仓库的权限。")
            
            # 通用建议
            summary.append("\n• 通用建议:")
            summary.append("  - 访问仓库主页手动下载失败的文件。")
            summary.append("  - 尝试使用 `ignore_patterns` 忽略特定问题文件或大文件。")
            summary.append("  - 查阅相关模型的HuggingFace社区或文档获取帮助。")
        
        return "\n".join(summary)

    def update_speed(self, bytes_added):
        # 计算并显示下载速度
        current_time = time.time()
        elapsed = current_time - self.last_update_time
        if elapsed > 1.0:  # 每秒更新一次
            speed = bytes_added / elapsed
            self.gui.status_var.set(f"下载速度：{format_size(speed)}/s")
            self.last_update_time = current_time
            self.total_bytes += bytes_added
    
    # 添加格式化文件大小的方法
    def _format_size(self, bytes):
        return format_size(bytes)

class HuggingFaceDownloaderGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("HuggingFace 模型下载器")
        self.root.geometry("780x680")  # 适当增大窗口
        self.root.minsize(750, 550)    # 设置最小窗口大小
        self.root.resizable(True, True)
        
        # 设置窗口图标 (如果有)
        try:
            # 如果有图标文件可以取消注释下面这行
            # self.root.iconbitmap("icon.ico")
            pass
        except:
            pass

        # 应用TTK主题
        self.style = ttk.Style(self.root)
        available_themes = self.style.theme_names()
        
        # 优先选择更现代的主题
        if 'vista' in available_themes:  # Windows
            self.style.theme_use('vista')
        elif 'clam' in available_themes:  # Good cross-platform
            self.style.theme_use('clam')
        elif 'aqua' in available_themes:  # macOS
            self.style.theme_use('aqua')
            
        # 自定义主题样式
        self.setup_custom_styles()
        
        # 创建下载跟踪器
        self.download_tracker = DownloadTracker(self)
        
        # 创建主滚动区域
        # 创建一个Canvas作为滚动区域
        self.canvas = tk.Canvas(root)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 添加滚动条
        scrollbar = ttk.Scrollbar(root, orient="vertical", command=self.canvas.yview)
        scrollbar.pack(side=tk.RIGHT, fill="y")
        
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.bind('<Configure>', lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        
        # 创建主框架
        main_frame = ttk.Frame(self.canvas, padding=15)
        self.canvas.create_window((0, 0), window=main_frame, anchor="nw")
        
        # 添加鼠标滚轮绑定
        self.root.bind("<MouseWheel>", self._on_mousewheel)  # Windows
        self.root.bind("<Button-4>", self._on_mousewheel)    # Linux 向上滚动
        self.root.bind("<Button-5>", self._on_mousewheel)    # Linux 向下滚动
        
        # 调整列配置，确保居中效果
        main_frame.columnconfigure(0, weight=1)
        
        # --- 配置输入区 ---
        input_frame = ttk.LabelFrame(main_frame, text="下载配置", padding=12)
        input_frame.grid(row=0, column=0, sticky=tk.EW, pady=(0,12))
        
        # 确保输入框能够扩展
        input_frame.columnconfigure(1, weight=1)

        # 仓库ID输入行
        ttk.Label(input_frame, text="仓库ID:", width=10).grid(row=0, column=0, sticky=tk.W, pady=8, padx=8)
        self.repo_id = tk.StringVar(value="Systran/faster-whisper-large-v2")
        repo_entry = ttk.Entry(input_frame, textvariable=self.repo_id, width=60)
        repo_entry.grid(row=0, column=1, sticky=tk.EW, pady=8, padx=5)
        self.repo_id.trace_add("write", self.update_default_save_path)
        repo_entry.bind("<Control-z>", lambda e: repo_entry.event_generate("<<Undo>>"))
        
        # 保存位置输入行
        ttk.Label(input_frame, text="保存位置:", width=10).grid(row=1, column=0, sticky=tk.W, pady=8, padx=8)
        self.local_dir = tk.StringVar()
        self.update_default_save_path()
        local_dir_entry = ttk.Entry(input_frame, textvariable=self.local_dir, width=60)
        local_dir_entry.grid(row=1, column=1, sticky=tk.EW, pady=8, padx=5)
        local_dir_entry.bind("<Control-z>", lambda e: local_dir_entry.event_generate("<<Undo>>"))
        
        # 浏览按钮
        browse_btn = ttk.Button(input_frame, text="浏览...", command=self.browse_directory, style="Normal.TButton", width=8)
        browse_btn.grid(row=1, column=2, padx=8, pady=8)
        
        # --- 代理设置 ---
        proxy_frame = ttk.LabelFrame(main_frame, text="代理设置", padding=12)
        proxy_frame.grid(row=1, column=0, sticky=tk.EW, pady=12)
        proxy_frame.columnconfigure(1, weight=1)

        # HTTP代理
        ttk.Label(proxy_frame, text="HTTP代理:", width=10).grid(row=0, column=0, sticky=tk.W, pady=8, padx=8)
        self.http_proxy = tk.StringVar(value="http://127.0.0.1:10100")
        http_proxy_entry = ttk.Entry(proxy_frame, textvariable=self.http_proxy)
        http_proxy_entry.grid(row=0, column=1, sticky=tk.EW, pady=8, padx=5)
        http_proxy_entry.bind("<Control-z>", lambda e: http_proxy_entry.event_generate("<<Undo>>"))
        
        # HTTPS代理
        ttk.Label(proxy_frame, text="HTTPS代理:", width=10).grid(row=1, column=0, sticky=tk.W, pady=8, padx=8)
        self.https_proxy = tk.StringVar(value="http://127.0.0.1:10100")
        https_proxy_entry = ttk.Entry(proxy_frame, textvariable=self.https_proxy)
        https_proxy_entry.grid(row=1, column=1, sticky=tk.EW, pady=8, padx=5)
        https_proxy_entry.bind("<Control-z>", lambda e: https_proxy_entry.event_generate("<<Undo>>"))
        
        # 启用代理复选框
        self.use_proxy = tk.BooleanVar(value=True)
        ttk.Checkbutton(proxy_frame, text="启用代理", variable=self.use_proxy, style="TCheckbutton").grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=5, padx=8)
        
        # --- 高级选项 ---
        advanced_frame = ttk.LabelFrame(main_frame, text="高级选项", padding=12)
        advanced_frame.grid(row=2, column=0, sticky=tk.EW, pady=12)
        advanced_frame.columnconfigure(1, weight=1)
        
        # 使用符号链接复选框
        self.use_symlinks = tk.BooleanVar(value=False)
        ttk.Checkbutton(advanced_frame, text="使用符号链接 (Windows不推荐)", variable=self.use_symlinks, style="TCheckbutton").grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=5, padx=8)
        
        # 断点续传复选框
        self.resume_download = tk.BooleanVar(value=True)
        ttk.Checkbutton(advanced_frame, text="断点续传", variable=self.resume_download, style="TCheckbutton").grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=5, padx=8)
        
        # 忽略文件模式
        ttk.Label(advanced_frame, text="忽略文件模式:", width=10).grid(row=2, column=0, sticky=tk.W, pady=8, padx=8)
        self.ignore_patterns = tk.StringVar()
        ignore_entry = ttk.Entry(advanced_frame, textvariable=self.ignore_patterns)
        ignore_entry.grid(row=2, column=1, sticky=tk.EW, pady=8, padx=5)
        ignore_entry.bind("<Control-z>", lambda e: ignore_entry.event_generate("<<Undo>>"))
        
        # 忽略文件模式提示
        hint_label = ttk.Label(advanced_frame, text="(逗号分隔, 例如: *.safetensors,*.pt,*.bin)", foreground="#666666")
        hint_label.grid(row=3, column=0, columnspan=2, sticky=tk.W, padx=18, pady=2)
        
        # HF Token
        ttk.Label(advanced_frame, text="HF Token:", width=10).grid(row=4, column=0, sticky=tk.W, pady=8, padx=8)
        self.hf_token = tk.StringVar()
        hf_token_entry = ttk.Entry(advanced_frame, textvariable=self.hf_token, show="*")
        hf_token_entry.grid(row=4, column=1, sticky=tk.EW, pady=8, padx=5)
        hf_token_entry.bind("<Control-z>", lambda e: hf_token_entry.event_generate("<<Undo>>"))

        # --- 操作按钮 ---
        button_frame = ttk.Frame(main_frame, padding=(0, 8, 0, 8))
        button_frame.grid(row=3, column=0, sticky=tk.EW, pady=8)
        
        # 居中按钮
        button_frame.columnconfigure(0, weight=1)
        button_frame.columnconfigure(3, weight=1)
        
        # 按钮容器 - 用于水平居中
        btn_container = ttk.Frame(button_frame)
        btn_container.grid(row=0, column=1, columnspan=2)
        
        # 开始下载按钮
        self.download_btn = ttk.Button(btn_container, text="开始下载", command=self.start_download, 
                                     style="Accent.TButton", width=12)
        self.download_btn.grid(row=0, column=0, padx=12, pady=5)
        
        # 取消下载按钮
        self.cancel_btn = ttk.Button(btn_container, text="取消下载", command=self.cancel_download, 
                                    state=tk.DISABLED, width=12)
        self.cancel_btn.grid(row=0, column=1, padx=12, pady=5)
        
        # --- 关于按钮 ----
        about_btn = ttk.Button(btn_container, text="关于", command=self.show_about, width=8)
        about_btn.grid(row=0, column=2, padx=12, pady=5)
        
        # --- 进度显示 ---
        progress_status_frame = ttk.LabelFrame(main_frame, text="下载状态", padding=12)
        progress_status_frame.grid(row=4, column=0, sticky=tk.EW, pady=12)
        progress_status_frame.columnconfigure(0, weight=1)

        # 进度条
        progress_frame = ttk.Frame(progress_status_frame)
        progress_frame.grid(row=0, column=0, sticky=tk.EW, pady=8)
        progress_frame.columnconfigure(0, weight=1)
        
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, 
                                           maximum=100, mode='determinate', style="TProgressbar")
        self.progress_bar.grid(row=0, column=0, sticky=tk.EW, pady=5, padx=5)
        
        # 进度百分比标签
        self.progress_label = ttk.Label(progress_frame, text="0.0%", width=8, anchor=tk.E)
        self.progress_label.grid(row=0, column=1, sticky=tk.E, pady=5, padx=5)
        
        # 状态显示
        self.status_var = tk.StringVar(value="就绪")
        status_label = ttk.Label(progress_status_frame, textvariable=self.status_var, 
                               wraplength=700, anchor=tk.W, style="Status.TLabel")
        status_label.grid(row=1, column=0, sticky=tk.EW, pady=5, padx=5)
        
        # --- 日志框 ---
        log_frame = ttk.LabelFrame(main_frame, text="下载日志", padding=12)
        log_frame.grid(row=5, column=0, sticky=tk.NSEW, pady=(12,0))
        main_frame.rowconfigure(5, weight=1)

        # 日志内框架
        log_inner_frame = ttk.Frame(log_frame)
        log_inner_frame.pack(fill=tk.BOTH, expand=True)
        
        # 滚动条
        scrollbar = ttk.Scrollbar(log_inner_frame, style="TScrollbar")
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 日志文本区域
        self.log_text = tk.Text(log_inner_frame, wrap=tk.WORD, height=8, 
                              yscrollcommand=scrollbar.set, relief=tk.FLAT, 
                              borderwidth=0, font=("微软雅黑", 9),
                              background="#f8f8f8", foreground="#333333")
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.log_text.yview)
        
        # --- 初始化和配置 ---
        # 绑定进度条更新
        self.progress_var.trace_add("write", self.update_progress_label_display)
        
        # 为文本组件启用撤销功能
        self.enable_undo_for_text_widgets()
        
        # 下载线程
        self.download_thread = None
        self.is_downloading = False
        
        # 自定义标签绑定，用于鼠标悬停效果
        self.customize_widget_bindings()
        
        # 设置初始焦点
        repo_entry.focus_set()
        
        # 中央日志信息
        self.log("欢迎使用 HuggingFace 模型下载器")
        self.log("请输入仓库ID并设置下载选项后开始下载")
    
    def _on_mousewheel(self, event):
        """处理鼠标滚轮事件"""
        # Windows鼠标滚轮
        if event.num == 5 or event.delta < 0:
            self.canvas.yview_scroll(1, "units")
        # Linux向上滚动或Windows向上滚动
        elif event.num == 4 or event.delta > 0:
            self.canvas.yview_scroll(-1, "units")
    
    def show_about(self):
        """显示关于对话框"""
        about_window = tk.Toplevel(self.root)
        about_window.title("关于")
        about_window.geometry("400x200")
        about_window.resizable(False, False)
        
        # 设置为模态窗口
        about_window.grab_set()
        about_window.transient(self.root)
        
        # 信息框架
        info_frame = ttk.Frame(about_window, padding=15)
        info_frame.pack(fill=tk.BOTH, expand=True)
        
        # 标题
        title_font = font.Font(family="微软雅黑", size=12, weight="bold")
        title = ttk.Label(info_frame, text="HuggingFace 模型下载器", font=title_font)
        title.pack(pady=(5, 10))
        
        # 作者信息
        author_frame = ttk.Frame(info_frame)
        author_frame.pack(pady=5)
        
        ttk.Label(author_frame, text="作者: ").pack(side=tk.LEFT)
        
        # 用超链接样式显示作者信息
        author_link = ttk.Label(author_frame, text="沧浪同学", foreground="#0078d7", cursor="hand2")
        author_link.pack(side=tk.LEFT)
        author_link.bind("<Button-1>", lambda e: webbrowser.open("https://space.bilibili.com/520050693"))
        
        # 版本信息
        ttk.Label(info_frame, text="版本: 1.0").pack(pady=5)
        
        # 描述
        description = ttk.Label(info_frame, text="一个简单易用的工具，用于从HuggingFace Hub下载模型和数据集。\n支持代理设置和断点续传功能。", 
                              wraplength=350, justify="center")
        description.pack(pady=10)
        
        # 确定按钮
        ttk.Button(info_frame, text="确定", command=about_window.destroy, width=10).pack(pady=10)
    
    def setup_custom_styles(self):
        """设置自定义样式"""
        # 获取系统默认字体
        default_font = font.nametofont("TkDefaultFont")
        default_family = default_font.actual()["family"]
        
        # 尝试设置更好的字体 - 如果可用的话
        try:
            system_fonts = font.families()
            preferred_fonts = ["微软雅黑", "Microsoft YaHei", "Arial", "Segoe UI", default_family]
            
            # 找到第一个可用的字体
            chosen_font = next((f for f in preferred_fonts if f in system_fonts), default_family)
            
            # 设置默认字体
            font_config = {"family": chosen_font, "size": 9}
            self.style.configure(".", font=font_config)
            
        except Exception:
            pass  # 如果字体设置失败，使用默认字体
        
        # 自定义按钮样式 - 修改背景和字体颜色
        self.style.configure("Accent.TButton", 
                            font=("微软雅黑", 9, "bold"),
                            background="#2f80ed", 
                            foreground="#000000") # 改为黑色字体以确保可见性
        
        self.style.map("Accent.TButton",
                     background=[('active', '#1e6fd9'), ('pressed', '#1a64c4')],
                     foreground=[('active', '#000000'), ('pressed', '#000000')], # 改为黑色
                     relief=[('pressed', 'sunken')])
                      
        self.style.configure("Normal.TButton", padding=4)
        
        # 自定义标签样式
        self.style.configure("Status.TLabel", foreground="#2f80ed", font=("微软雅黑", 9, "bold"))
        
        # 自定义标签框架
        self.style.configure("TLabelframe.Label", font=("微软雅黑", 9, "bold"))
        
        # 自定义复选框
        self.style.configure("TCheckbutton", font=("微软雅黑", 9))
        
        # 自定义进度条
        self.style.configure("TProgressbar", background="#2f80ed", troughcolor="#f0f0f0", 
                           borderwidth=0, thickness=16)
    
    def customize_widget_bindings(self):
        """为组件添加自定义绑定以增强交互性"""
        # 为按钮添加鼠标悬停效果
        for widget in [self.download_btn, self.cancel_btn]:
            widget.bind("<Enter>", lambda e, w=widget: self.on_widget_enter(e, w))
            widget.bind("<Leave>", lambda e, w=widget: self.on_widget_leave(e, w))
    
    def on_widget_enter(self, event, widget):
        """鼠标进入组件时的效果"""
        if widget.cget("state") != "disabled":
            # 可以添加悬停效果，但目前ttk样式映射已经处理了这部分
            pass
    
    def on_widget_leave(self, event, widget):
        """鼠标离开组件时的效果"""
        if widget.cget("state") != "disabled":
            # 可以添加离开效果，但目前ttk样式映射已经处理了这部分
            pass
    
    def update_progress_label_display(self, *args):
        """更新进度条旁边的百分比标签"""
        progress = self.progress_var.get()
        
        # 限制最大进度为100%
        if progress > 100:
            progress = 100
            self.progress_var.set(100)
        
        # 进度条处于不确定状态时显示为动画中，不显示具体百分比
        if self.progress_bar.cget('mode') == 'indeterminate':
            self.progress_label.config(text="下载中")
        else:
            self.progress_label.config(text=f"{progress:.1f}%")
    
    def update_default_save_path(self, *args):
        repo_id = self.repo_id.get()
        if repo_id:
            parts = repo_id.split('/')
            repo_name = parts[-1] if len(parts) > 1 else repo_id
            self.local_dir.set(os.path.join(".", repo_name))
    
    def enable_undo_for_text_widgets(self):
        for widget in self.root.winfo_children():
            self._enable_undo_recursively(widget)
        self.root.option_add('*Text.maxUndo', 100)
        self.root.option_add('*Text.undoLevel', 100)
    
    def _enable_undo_recursively(self, widget):
        if isinstance(widget, (tk.Entry, ttk.Entry, tk.Text)):
            try:
                widget.config(undo=True)
            except tk.TclError:
                pass 
        for child in widget.winfo_children():
            self._enable_undo_recursively(child)
    
    def browse_directory(self):
        directory = filedialog.askdirectory()
        if directory:
            repo_parts = self.repo_id.get().split('/')
            default_dir_name = repo_parts[-1] if len(repo_parts) > 1 else self.repo_id.get()
            full_path = os.path.join(directory, default_dir_name)
            self.local_dir.set(full_path)
    
    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_message = f"[{timestamp}] {message}"
        
        self.log_text.configure(state='normal')
        self.log_text.insert(tk.END, formatted_message + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state='disabled')
        self.root.update_idletasks()
    
    def cancel_download(self):
        if self.is_downloading:
            self.is_downloading = False
            self.log("用户请求取消下载...")
            self.status_var.set("正在取消下载...")
            self.cancel_btn.config(state=tk.DISABLED)

    def start_download(self):
        self.log_text.configure(state='normal')
        self.log_text.delete(1.0, tk.END)
        self.log_text.configure(state='disabled')
        
        repo_id = self.repo_id.get().strip()
        local_dir = self.local_dir.get().strip()
        
        if not repo_id:
            messagebox.showerror("错误", "请输入有效的仓库ID。")
            return
        
        if not local_dir:
            messagebox.showerror("错误", "请选择保存位置。")
            return
        
        # Proxy setup
        if self.use_proxy.get():
            http_p = self.http_proxy.get().strip()
            https_p = self.https_proxy.get().strip()
            os.environ['HTTP_PROXY'] = http_p
            os.environ['HTTPS_PROXY'] = https_p
            self.log(f"已设置代理: HTTP='{http_p}', HTTPS='{https_p}'")
        else:
            if 'HTTP_PROXY' in os.environ: del os.environ['HTTP_PROXY']
            if 'HTTPS_PROXY' in os.environ: del os.environ['HTTPS_PROXY']
            self.log("未使用代理。")
        
        ignore_patterns_str = self.ignore_patterns.get().strip()
        ignore_patterns = [pat.strip() for pat in ignore_patterns_str.split(',') if pat.strip()] if ignore_patterns_str else None
        if ignore_patterns: self.log(f"忽略文件模式: {', '.join(ignore_patterns)}")
        
        self.is_downloading = True
        self.download_btn.config(state=tk.DISABLED)
        self.cancel_btn.config(state=tk.NORMAL)
        
        self.progress_var.set(0)
        
        self.download_tracker.start()
        
        self.download_thread = threading.Thread(
            target=self.download_task,
            args=(repo_id, local_dir, ignore_patterns)
        )
        self.download_thread.daemon = True
        self.download_thread.start()
    
    def extract_file_from_url(self, url):
        match = re.search(r'huggingface\.co/[^/]+/[^/]+/resolve/[^/]+/(.+)', url)
        return match.group(1) if match else url
    
    def get_direct_download_url(self, repo_id, filename):
        filename = filename[1:] if filename.startswith('/') else filename
        return f"https://huggingface.co/{repo_id}/resolve/main/{filename}"
    
    def download_task(self, repo_id, local_dir, ignore_patterns):
        """执行下载任务的主函数"""
        repo_url = f"https://huggingface.co/{repo_id}"
        token_to_use = self.hf_token.get().strip() or os.environ.get("HF_TOKEN")

        try:
            self.log(f"仓库主页: {repo_url}")
            self.log(f"开始下载 {repo_id} 到 {local_dir}...")
            
            # 获取仓库文件数量以便估计进度
            try:
                files = list_repo_files(repo_id, token=token_to_use, repo_type="model")
                self.download_tracker.set_total_files(len(files))
            except Exception as e:
                self.log(f"获取仓库文件列表失败: {str(e)}")
                # 继续尝试下载，但无法准确显示进度
            
            os.makedirs(local_dir, exist_ok=True)
            
            if not self.is_downloading: # 用户可能在此期间取消下载
                self.log("下载在开始前被取消。")
                self.status_var.set("下载已取消")
                self.download_tracker.end()
                self.progress_var.set(0)
                return

            # 注意：snapshot_download不支持download_callback参数
            snapshot_download(
                repo_id=repo_id,
                local_dir=local_dir,
                local_dir_use_symlinks=self.use_symlinks.get(),
                resume_download=self.resume_download.get(),
                ignore_patterns=ignore_patterns,
                token=token_to_use,
                # 移除了不兼容的download_callback参数
            )
            
            if self.is_downloading:
                self.log(f"下载流程执行完毕。文件已保存在: {local_dir}")
                self.status_var.set("下载完成")
                self.progress_var.set(100) # 设为100%表示完成

            # 在函数适当位置添加计数器变量
            successful_files_count = 0
            
            # 在成功下载后更新
            self.log(f"成功下载：{successful_files_count}/{self.download_tracker.total_files}个文件")

        except HfHubHTTPError as e:
            if not self.is_downloading: return
            error_message = str(e)
            self.log(f"下载HTTP错误: {error_message}")
            
            # 尝试从错误消息中找出失败的文件URL
            urls = re.findall(r'https://huggingface.co/[^\s\'\"]+', error_message)
            if urls:
                for url in urls:
                    filename = self.extract_file_from_url(url)
                    self.download_tracker.add_failed_file(filename, f"HTTP错误: {e.response.status_code if hasattr(e, 'response') and e.response else 'N/A'}")
            else:
                self.download_tracker.add_failed_file("未知文件 (HTTP错误)", error_message)
                
            self.status_var.set("下载因HTTP错误失败")
        
        except urllib3.exceptions.IncompleteRead as e:
            if not self.is_downloading: return
            self.log(f"连接中断 (IncompleteRead): 数据接收不完整。")
            self.log(f"  已接收: {len(e.partial) if hasattr(e, 'partial') else '未知'} 字节")
            self.log(f"  预计大小: {e.expected if hasattr(e, 'expected') else '未知'} 字节")
            
            self.download_tracker.add_failed_file("未知文件 (网络中断)", 
                                          f"数据传输中断: 接收了{len(e.partial) if hasattr(e, 'partial') else '未知'}字节")
            self.status_var.set("下载因连接中断失败")
            
        except Exception as e:
            if not self.is_downloading: return
            error_message = str(e)
            self.log(f"发生未知错误: {error_message}")
            
            self.download_tracker.add_failed_file("未知文件 (发生错误)", error_message)
            self.status_var.set("下载因未知错误失败")
        
        finally:
            # 结束进度跟踪
            self.download_tracker.end()
            
            # 如果用户取消但状态未更新，则更新状态
            if not self.is_downloading and self.status_var.get() != "下载已取消":
                 self.log("下载任务在处理过程中被取消。")
                 self.status_var.set("下载已取消")

            # 生成并显示下载摘要
            summary = self.download_tracker.get_summary()
            self.log("\n" + summary)
            
            # 恢复按钮状态
            self.is_downloading = False
            self.download_btn.config(state=tk.NORMAL)
            self.cancel_btn.config(state=tk.DISABLED)
            
            # 根据下载状态显示不同的消息框
            current_status = self.status_var.get()
            if current_status == "下载完成" and not self.download_tracker.failed_files:
                 messagebox.showinfo("下载完成", f"所有文件已成功下载!\n保存在: {local_dir}")
            elif "完成" in current_status and self.download_tracker.failed_files:
                 messagebox.showwarning("部分完成", f"下载完成，但有{len(self.download_tracker.failed_files)}个文件失败。\n请查看日志获取详情。\n保存在: {local_dir}")
            elif current_status == "下载已取消":
                 messagebox.showinfo("下载取消", "下载任务已被用户取消。")
            else: # 错误情况
                 messagebox.showerror("下载失败", "下载过程中遇到错误，请查看日志获取详情。")

if __name__ == "__main__":
    root = tk.Tk()
    app = HuggingFaceDownloaderGUI(root)
    root.mainloop()