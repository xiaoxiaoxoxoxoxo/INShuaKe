# gui_main.py
"""
刷课程序图形界面主入口 - 最终修复版（带定时功能）
"""
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import subprocess
import threading
import os
import sys
import re
from pathlib import Path
from datetime import datetime, time
import signal
import asyncio
import importlib.util
import warnings
import ctypes
import io
import time as timelib
warnings.filterwarnings("ignore")

# 判断是否在打包环境中
IS_FROZEN = getattr(sys, 'frozen', False)

# 隐藏控制台窗口（仅在打包环境中）
if IS_FROZEN and sys.platform == 'win32':
    try:
        ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
    except:
        pass

# 设置控制台编码（仅在开发环境中）
if not IS_FROZEN and sys.platform == 'win32':
    try:
        import codecs
        if sys.stdout and hasattr(sys.stdout, 'buffer'):
            sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'ignore')
        if sys.stderr and hasattr(sys.stderr, 'buffer'):
            sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'ignore')
    except:
        pass
    
    # Windows 异步策略设置
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

if IS_FROZEN:
    # 打包环境：确保路径正确
    base_path = os.path.dirname(sys.executable)
    if base_path not in sys.path:
        sys.path.insert(0, base_path)
    os.chdir(base_path)
    print(f"打包环境，工作目录: {base_path}")


class ConfigManager:
    """配置文件管理器"""
    
    # 根据运行环境确定配置文件路径
    if IS_FROZEN:
        # 打包后：配置文件在exe同目录
        CONFIG_PATH = Path(os.path.dirname(sys.executable)) / "config" / "config.py"
    else:
        # 开发环境：配置文件在项目目录
        CONFIG_PATH = Path("config/config.py")
    
    @classmethod
    def read_config(cls):
        """读取配置文件"""
        default_config = {
            'USER_NUMBER': '',
            'USER_PASSWD': '',
            'COURSER_LINK': 'https://www.hngbwlxy.gov.cn/#/courseCenter/courselist?channelId=',
            'ENABLE_TEMPLATE_CAPTURE': 'False',
            'HEADLESS_MODE': 'False',
            'DEBUG_MODE': 'True',
            'AUTO_START_ENABLED': 'False',  # 定时开关
            'AUTO_START_TIME': '06:00'       # 定时时间
        }
        
        try:
            # 确保配置目录存在
            cls.CONFIG_PATH.parent.mkdir(exist_ok=True, parents=True)
            
            if not cls.CONFIG_PATH.exists():
                cls.write_config(**default_config)
                return default_config
            
            with open(cls.CONFIG_PATH, 'r', encoding='utf-8') as f:
                content = f.read()
            
            config = {}
            for key in default_config.keys():
                pattern = rf'{key}\s*=\s*(.+?)(?:\n|$)'
                match = re.search(pattern, content)
                if match:
                    value = match.group(1).strip()
                    # 处理字符串值（去除引号）
                    if value.startswith(('"', "'")) and value.endswith(('"', "'")):
                        value = value[1:-1]
                    # 处理布尔值
                    elif value in ['True', 'False']:
                        value = value
                    config[key] = value
                else:
                    config[key] = default_config[key]
            
            return config
            
        except Exception as e:
            print(f"读取配置文件出错: {e}")
            return default_config
    
    @classmethod
    def write_config(cls, **kwargs):
        """写入配置文件"""
        try:
            cls.CONFIG_PATH.parent.mkdir(exist_ok=True, parents=True)
            
            content = f"""# config.py - 自动生成的配置文件
# 账号配置
USER_NUMBER = "{kwargs.get('USER_NUMBER', '')}"
USER_PASSWD = "{kwargs.get('USER_PASSWD', '')}"

# 课程链接配置
COURSER_LINK = "{kwargs.get('COURSER_LINK', 'https://www.hngbwlxy.gov.cn/#/courseCenter/courselist?channelId=')}"

# 功能开关配置
ENABLE_TEMPLATE_CAPTURE = {kwargs.get('ENABLE_TEMPLATE_CAPTURE', 'False')}
HEADLESS_MODE = {kwargs.get('HEADLESS_MODE', 'False')}
DEBUG_MODE = {kwargs.get('DEBUG_MODE', 'True')}

# 定时任务配置
AUTO_START_ENABLED = {kwargs.get('AUTO_START_ENABLED', 'False')}
AUTO_START_TIME = "{kwargs.get('AUTO_START_TIME', '06:00')}"
"""
            
            with open(cls.CONFIG_PATH, 'w', encoding='utf-8') as f:
                f.write(content)
            
            return True
        except Exception as e:
            print(f"写入配置文件出错: {e}")
            return False


class RedirectText:
    """重定向输出到文本框 - 线程安全的版本"""
    
    def __init__(self, text_widget):
        self.text_widget = text_widget
        self.queue = []
        self.lock = threading.Lock()
    
    def write(self, string):
        try:
            if string:
                with self.lock:
                    self.queue.append(string)
                # 在主线程中更新UI
                self.text_widget.after(0, self._process_queue)
        except Exception as e:
            print(f"重定向写入错误: {e}")
    
    def _process_queue(self):
        try:
            with self.lock:
                for string in self.queue:
                    self.text_widget.insert(tk.END, string)
                    self.text_widget.see(tk.END)
                self.queue.clear()
        except Exception as e:
            print(f"处理队列错误: {e}")
    
    def flush(self):
        pass


class ShuakeGUI:
    """刷课程序图形界面"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("作者：笑笑")
        self.root.geometry("900x750")
        self.root.resizable(True, True)
        
        # 设置图标
        try:
            icon_path = Path(__file__).parent / "icon.ico"
            if icon_path.exists():
                self.root.iconbitmap(str(icon_path))
        except:
            pass
        
        # 进程相关
        self.process = None
        self.process_thread = None
        self.is_running = False
        self.shuake_instance = None
        self.timer_thread = None
        self.timer_running = False
        
        # 加载配置
        self.config = ConfigManager.read_config()
        
        # 创建界面
        self.create_widgets()
        
        # 绑定关闭事件
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # 启动定时器检查线程
        self.start_timer_check()
    
    def create_widgets(self):
        """创建界面组件"""
        
        # 创建主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 配置网格权重
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        
        # ========== 配置输入区域 ==========
        config_frame = ttk.LabelFrame(main_frame, text="配置信息", padding="10")
        config_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        config_frame.columnconfigure(1, weight=1)
        
        # 账号
        ttk.Label(config_frame, text="账号:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.username_var = tk.StringVar(value=self.config.get('USER_NUMBER', ''))
        username_entry = ttk.Entry(config_frame, textvariable=self.username_var, width=50)
        username_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        
        # 密码
        ttk.Label(config_frame, text="密码:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.password_var = tk.StringVar(value=self.config.get('USER_PASSWD', ''))
        password_entry = ttk.Entry(config_frame, textvariable=self.password_var, width=50, show="*")
        password_entry.grid(row=1, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        
        # 学习网站
        ttk.Label(config_frame, text="学习网站:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.course_link_var = tk.StringVar(value=self.config.get('COURSER_LINK', ''))
        course_entry = ttk.Entry(config_frame, textvariable=self.course_link_var, width=50)
        course_entry.grid(row=2, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        
        # 保存设置按钮
        save_btn = ttk.Button(config_frame, text="保存设置", command=self.save_config)
        save_btn.grid(row=3, column=0, columnspan=2, pady=10)
        
        # ========== 开关控制区域 ==========
        switch_frame = ttk.LabelFrame(main_frame, text="功能开关", padding="10")
        switch_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        # 模板采集开关
        self.template_var = tk.BooleanVar(value=self.config.get('ENABLE_TEMPLATE_CAPTURE') == 'True')
        ttk.Checkbutton(switch_frame, text="启用模板采集", 
                       variable=self.template_var).grid(row=0, column=0, sticky=tk.W, pady=2)
        
        # 无窗口模式开关
        self.headless_var = tk.BooleanVar(value=self.config.get('HEADLESS_MODE') == 'True')
        ttk.Checkbutton(switch_frame, text="无窗口模式", 
                       variable=self.headless_var).grid(row=1, column=0, sticky=tk.W, pady=2)
        
        # 调试模式开关
        self.debug_var = tk.BooleanVar(value=self.config.get('DEBUG_MODE') == 'True')
        ttk.Checkbutton(switch_frame, text="调试模式", 
                       variable=self.debug_var).grid(row=2, column=0, sticky=tk.W, pady=2)
        
        # 应用开关按钮
        apply_switch_btn = ttk.Button(switch_frame, text="应用开关设置", command=self.apply_switches)
        apply_switch_btn.grid(row=3, column=0, pady=10)
        
        # ========== 定时任务区域 ==========
        timer_frame = ttk.LabelFrame(main_frame, text="定时任务", padding="10")
        timer_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        # 定时开关
        self.auto_start_var = tk.BooleanVar(value=self.config.get('AUTO_START_ENABLED') == 'True')
        ttk.Checkbutton(timer_frame, text="早上6点自动开启学习", 
                       variable=self.auto_start_var,
                       command=self.toggle_timer).grid(row=0, column=0, sticky=tk.W, pady=2)
        
        # 定时时间设置（支持自定义时间）
        ttk.Label(timer_frame, text="定时时间:").grid(row=1, column=0, sticky=tk.W, pady=2)
        
        time_frame = ttk.Frame(timer_frame)
        time_frame.grid(row=1, column=1, sticky=tk.W, padx=5, pady=2)
        
        self.hour_var = tk.StringVar(value=self.config.get('AUTO_START_TIME', '06:00').split(':')[0])
        self.minute_var = tk.StringVar(value=self.config.get('AUTO_START_TIME', '06:00').split(':')[1])
        
        hour_spinbox = ttk.Spinbox(time_frame, from_=0, to=23, width=5, textvariable=self.hour_var, format="%02.0f")
        hour_spinbox.grid(row=0, column=0)
        ttk.Label(time_frame, text=":").grid(row=0, column=1)
        minute_spinbox = ttk.Spinbox(time_frame, from_=0, to=59, width=5, textvariable=self.minute_var, format="%02.0f")
        minute_spinbox.grid(row=0, column=2)
        
        # 当前定时状态显示
        self.timer_status_var = tk.StringVar(value="定时任务: 未启用")
        ttk.Label(timer_frame, textvariable=self.timer_status_var, foreground="blue").grid(row=2, column=0, columnspan=2, pady=5)
        
        # ========== 控制按钮区域 ==========
        control_frame = ttk.Frame(main_frame)
        control_frame.grid(row=3, column=0, columnspan=2, pady=10)
        
        self.start_btn = ttk.Button(control_frame, text="开始学习", command=self.start_learning, width=15)
        self.start_btn.grid(row=0, column=0, padx=5)
        
        self.stop_btn = ttk.Button(control_frame, text="停止学习", command=self.stop_learning, width=15, state=tk.DISABLED)
        self.stop_btn.grid(row=0, column=1, padx=5)
        
        self.clear_btn = ttk.Button(control_frame, text="清空日志", command=self.clear_log, width=15)
        self.clear_btn.grid(row=0, column=2, padx=5)
        
        # ========== 日志显示区域 ==========
        log_frame = ttk.LabelFrame(main_frame, text="运行日志", padding="10")
        log_frame.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        
        # 创建文本框和滚动条
        self.log_text = scrolledtext.ScrolledText(log_frame, height=15, wrap=tk.WORD)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 配置文本框标签样式
        self.log_text.tag_config("error", foreground="red")
        self.log_text.tag_config("success", foreground="green")
        self.log_text.tag_config("info", foreground="blue")
        self.log_text.tag_config("warning", foreground="orange")
        
        # 重定向输出 - 使用线程安全的版本
        self.redirect = RedirectText(self.log_text)
        sys.stdout = self.redirect
        sys.stderr = self.redirect
        
        # 状态栏
        self.status_var = tk.StringVar(value="就绪")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.grid(row=5, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
    
    def save_config(self):
        """保存配置"""
        config_data = {
            'USER_NUMBER': self.username_var.get().strip(),
            'USER_PASSWD': self.password_var.get().strip(),
            'COURSER_LINK': self.course_link_var.get().strip(),
            'ENABLE_TEMPLATE_CAPTURE': str(self.template_var.get()),
            'HEADLESS_MODE': str(self.headless_var.get()),
            'DEBUG_MODE': str(self.debug_var.get()),
            'AUTO_START_ENABLED': str(self.auto_start_var.get()),
            'AUTO_START_TIME': f"{int(self.hour_var.get()):02d}:{int(self.minute_var.get()):02d}"
        }
        
        if ConfigManager.write_config(**config_data):
            messagebox.showinfo("成功", "配置保存成功！")
            self.status_var.set("配置已保存")
            self.update_timer_status()
        else:
            messagebox.showerror("错误", "配置保存失败！")
    
    def apply_switches(self):
        """应用开关设置"""
        config_data = ConfigManager.read_config()
        config_data['ENABLE_TEMPLATE_CAPTURE'] = str(self.template_var.get())
        config_data['HEADLESS_MODE'] = str(self.headless_var.get())
        config_data['DEBUG_MODE'] = str(self.debug_var.get())
        config_data['AUTO_START_ENABLED'] = str(self.auto_start_var.get())
        config_data['AUTO_START_TIME'] = f"{int(self.hour_var.get()):02d}:{int(self.minute_var.get()):02d}"
        
        if ConfigManager.write_config(**config_data):
            messagebox.showinfo("成功", "开关设置已应用！")
            self.status_var.set("开关设置已应用")
            self.update_timer_status()
        else:
            messagebox.showerror("错误", "开关设置失败！")
    
    def toggle_timer(self):
        """切换定时器状态"""
        self.save_config()
        if self.auto_start_var.get():
            self.log_text.insert(tk.END, f"定时任务已开启，将在每天 {int(self.hour_var.get()):02d}:{int(self.minute_var.get()):02d} 自动开始学习\n", "info")
        else:
            self.log_text.insert(tk.END, "定时任务已关闭\n", "warning")
        self.update_timer_status()
    
    def update_timer_status(self):
        """更新定时器状态显示"""
        if self.auto_start_var.get():
            self.timer_status_var.set(f"定时任务: 已开启 (每天 {int(self.hour_var.get()):02d}:{int(self.minute_var.get()):02d} 自动开始)")
        else:
            self.timer_status_var.set("定时任务: 未启用")
    
    def start_timer_check(self):
        """启动定时检查线程"""
        self.timer_running = True
        self.timer_thread = threading.Thread(target=self.check_timer, daemon=True)
        self.timer_thread.start()
    
    def check_timer(self):
        """检查定时任务"""
        while self.timer_running:
            try:
                if self.auto_start_var.get() and not self.is_running:
                    current_time = datetime.now().time()
                    target_hour = int(self.hour_var.get())
                    target_minute = int(self.minute_var.get())
                    target_time = time(target_hour, target_minute)
                    
                    # 检查是否到达指定时间（允许1分钟的误差）
                    if (current_time.hour == target_time.hour and 
                        current_time.minute == target_time.minute):
                        
                        self.root.after(0, self.auto_start_learning)
                        
                        # 避免重复触发，等待一分钟
                        timelib.sleep(60)
                
                # 每秒检查一次
                timelib.sleep(1)
                
            except Exception as e:
                print(f"定时检查错误: {e}")
                timelib.sleep(5)
    
    def auto_start_learning(self):
        """自动开始学习"""
        self.log_text.insert(tk.END, f"\n{'='*60}\n", "info")
        self.log_text.insert(tk.END, f"定时任务触发 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n", "success")
        self.log_text.insert(tk.END, f"{'='*60}\n\n", "info")
        
        if not self.is_running:
            self.start_learning()
    
    def start_learning(self):
        """开始学习"""
        if self.is_running:
            messagebox.showwarning("警告", "程序已在运行中！")
            return
        
        # 先保存当前配置
        self.save_config()
        
        # 启动线程运行主程序
        self.is_running = True
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        
        self.status_var.set("正在运行中...")
        self.log_text.insert(tk.END, f"\n{'='*60}\n")
        self.log_text.insert(tk.END, f"开始学习 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        self.log_text.insert(tk.END, f"{'='*60}\n\n")
        
        self.process_thread = threading.Thread(target=self.run_shuake, daemon=True)
        self.process_thread.start()
    
    def run_shuake(self):
        """运行刷课核心程序 - 修复输出问题"""
        try:
            if IS_FROZEN:
                # 打包环境 - 直接在当前进程运行
                work_dir = os.path.dirname(sys.executable)
                
                # 添加路径到系统路径
                if work_dir not in sys.path:
                    sys.path.insert(0, work_dir)
                
                # 直接导入并运行Shuake
                try:
                    # 尝试直接导入
                    from Shuake import Shuake
                except ImportError as e:
                    # 尝试从文件导入
                    shuake_path = os.path.join(work_dir, "Shuake.py")
                    if os.path.exists(shuake_path):
                        spec = importlib.util.spec_from_file_location("Shuake", shuake_path)
                        shuake_module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(shuake_module)
                        Shuake = shuake_module.Shuake
                    else:
                        self.log_text.insert(tk.END, f"错误: 找不到Shuake.py文件\n", "error")
                        return
                
                # 设置Windows异步策略
                if sys.platform == 'win32':
                    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
                
                # 创建Shuake实例
                shuake = Shuake()
                self.shuake_instance = shuake
                
                # 在新线程中运行异步任务
                def run_async():
                    try:
                        # 创建新的事件循环
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        
                        # 运行主程序
                        loop.run_until_complete(shuake.start())
                        
                    except Exception as e:
                        error_msg = f"运行错误: {str(e)}"
                        self.log_text.insert(tk.END, error_msg + "\n", "error")
                    finally:
                        try:
                            loop.close()
                        except:
                            pass
                        self.root.after(0, self.on_process_finished)
                
                # 启动线程
                thread = threading.Thread(target=run_async, daemon=True)
                thread.start()
                
            else:
                # 开发环境 - 使用子进程运行
                python_path = sys.executable
                shuake_path = os.path.join(os.path.dirname(__file__), "Shuake.py")
                
                self.process = subprocess.Popen(
                    [python_path, shuake_path],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    bufsize=1,
                    cwd=os.path.dirname(__file__),
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
                )
                
                # 实时读取输出
                while True:
                    try:
                        line = self.process.stdout.readline()
                        if not line:
                            break
                        
                        # 解码输出
                        if isinstance(line, bytes):
                            try:
                                line = line.decode('utf-8', errors='ignore')
                            except:
                                line = line.decode('gbk', errors='ignore')
                        
                        # 显示输出
                        self.log_text.insert(tk.END, line)
                        self.log_text.see(tk.END)
                        self.log_text.update_idletasks()
                        
                    except Exception as e:
                        break
                
                # 等待进程结束
                self.process.wait()
                self.root.after(0, self.on_process_finished)
                
        except Exception as e:
            self.log_text.insert(tk.END, f"运行错误: {e}\n", "error")
            self.root.after(0, self.on_process_finished)
    
    def on_process_finished(self):
        """进程结束后的处理"""
        self.is_running = False
        self.shuake_instance = None
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.status_var.set("运行完成")
        
        self.log_text.insert(tk.END, f"\n{'='*60}\n")
        self.log_text.insert(tk.END, f"学习结束 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        self.log_text.insert(tk.END, f"{'='*60}\n\n")
    
    def stop_learning(self):
        """停止学习"""
        if IS_FROZEN:
            # 打包环境
            if self.shuake_instance:
                try:
                    self.log_text.insert(tk.END, "\n正在停止程序...\n", "info")
                    # 强制退出
                    os._exit(0)
                except Exception as e:
                    self.log_text.insert(tk.END, f"停止程序时出错: {e}\n", "error")
        else:
            # 开发环境
            if self.process and self.process.poll() is None:
                try:
                    self.process.terminate()
                    self.process.wait(timeout=5)
                    self.log_text.insert(tk.END, "\n用户终止程序\n", "error")
                    self.status_var.set("已停止")
                except Exception as e:
                    self.log_text.insert(tk.END, f"停止程序时出错: {e}\n", "error")
        
        self.is_running = False
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
    
    def clear_log(self):
        """清空日志"""
        self.log_text.delete(1.0, tk.END)
    
    def on_closing(self):
        """关闭窗口时的处理"""
        self.timer_running = False
        if self.is_running:
            if messagebox.askyesno("确认", "程序正在运行中，确定要退出吗？"):
                self.stop_learning()
                if self.process_thread and self.process_thread.is_alive():
                    self.process_thread.join(timeout=2)
                if self.timer_thread and self.timer_thread.is_alive():
                    self.timer_thread.join(timeout=1)
                self.root.destroy()
        else:
            if self.timer_thread and self.timer_thread.is_alive():
                self.timer_thread.join(timeout=1)
            self.root.destroy()


def main():
    """主函数"""
    root = tk.Tk()
    app = ShuakeGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
