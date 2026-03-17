# Shuake.py
from progressbar import ProgressBar, Percentage, Bar
from playwright.async_api import async_playwright
from config.config import (
    USER_NUMBER,
    USER_PASSWD,
    COURSER_LINK,
    ENABLE_TEMPLATE_CAPTURE,
    HEADLESS_MODE,
    DEBUG_MODE
)
from getcourseid import Get_course_id, Get_all_course_ids
from cdb import CourseDatabase
import asyncio as asynioc
import cv2
import re
import base64
import os
import random
import time
import numpy as np
from collections import Counter
from datetime import datetime

# ==================== 统一日志函数 ====================
def log_message(message, level="INFO", show_time=True):
    """
    统一日志打印函数
    :param message: 日志内容
    :param level: 日志级别 (DEBUG, INFO, WARN, ERROR, SUCCESS)
    :param show_time: 是否显示时间戳
    """
    # 颜色代码
    colors = {
        "DEBUG": "\033[90m",    # 灰色
        "INFO": "\033[0m",      # 白色
        "WARN": "\033[33m",     # 黄色
        "ERROR": "\033[91m",    # 红色
        "SUCCESS": "\033[92m",  # 绿色
    }
    
    color_end = "\033[0m"
    
    if show_time:
        timestamp = datetime.now().strftime("%H:%M:%S")
        prefix = f"[{timestamp}] [{level}]"
    else:
        prefix = f"[{level}]"
    
    log_line = f"{prefix} {message}"
    
    if level in colors:
        log_line = f"{colors[level]}{log_line}{color_end}"
    
    print(log_line)
    return log_line

# ==================== 模板采集与缺口识别模块 ====================
TEMPLATE_DIR = "./templates"
DEBUG_DIR = "./debug"

def create_template_dir():
    """确保模板目录存在"""
    if not os.path.exists(TEMPLATE_DIR):
        os.makedirs(TEMPLATE_DIR)
    if not os.path.exists(DEBUG_DIR):
        os.makedirs(DEBUG_DIR)

def dhash(image, hash_size=8):
    """计算图片的感知哈希（用于去重）"""
    resized = cv2.resize(image, (hash_size + 1, hash_size))
    diff = resized[:, 1:] > resized[:, :-1]
    return ''.join(['1' if b else '0' for b in diff.flatten()])

def hamming_distance(h1, h2):
    """计算两个哈希值的汉明距离"""
    return sum(ch1 != ch2 for ch1, ch2 in zip(h1, h2))

def crop_roi(image, gap_x, roi_width=60, roi_height=60):
    """根据缺口位置裁剪感兴趣区域"""
    h, w = image.shape[:2]
    x1 = max(0, gap_x - roi_width // 2)
    x2 = min(w, gap_x + roi_width // 2)
    y1 = max(0, h // 4)
    y2 = min(h, h // 4 * 3)
    return image[y1:y2, x1:x2]

class CaptchaSolver:
    """验证码识别类：优先模板匹配，失败则回退到轮廓法"""
    def __init__(self):
        self.templates = []
        self.scale = 1.0
        create_template_dir()
        # 加载 ./templates 目录下的所有模板
        for file in os.listdir(TEMPLATE_DIR):
            if file.endswith(('.png', '.jpg')):
                tmpl = cv2.imread(os.path.join(TEMPLATE_DIR, file), 0)
                if tmpl is not None:
                    if tmpl.shape[0] < 200 and tmpl.shape[1] < 200:
                        self.templates.append(tmpl)
        log_message(f"已加载 {len(self.templates)} 个模板", "INFO")

    def get_gap_position(self, image):
        # 优先模板匹配
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image
        best_x, best_score = None, 0
        for tmpl in self.templates:
            if len(tmpl.shape) == 3:
                tmpl_gray = cv2.cvtColor(tmpl, cv2.COLOR_BGR2GRAY)
            else:
                tmpl_gray = tmpl
            if gray.shape[0] < tmpl_gray.shape[0] or gray.shape[1] < tmpl_gray.shape[1]:
                continue
            res = cv2.matchTemplate(gray, tmpl_gray, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            if max_val > 0.6:
                best_score = max_val
                best_x = max_loc[0] + tmpl_gray.shape[1] // 2
        if best_score > 0.6:
            return int(best_x * self.scale)
        # 回退到轮廓法
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 50, 150)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        positions = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if 300 < area < 5000:
                x, y, w, h = cv2.boundingRect(cnt)
                if x > gray.shape[1] * 0.3:
                    positions.append(x + w // 2)
        if positions:
            counter = Counter(positions)
            most_common = counter.most_common(1)[0][0]
            return int(most_common * self.scale)
        return None

# ==================== 自动采集模板函数 ====================
async def auto_capture_templates(page, solver, min_high_quality=20, max_attempts=100):
    """
    自动采集高质量缺口模板
    功能：
    1. 从页面截取验证码图片
    2. 用轮廓法找到缺口位置
    3. 裁剪缺口区域保存到 ./templates
    4. 用感知哈希去重，完全相同的图片覆盖
    5. 达到 min_high_quality 数量后自动停止
    """
    create_template_dir()
    existing_hashes = []
    for file in os.listdir(TEMPLATE_DIR):
        if file.endswith(('.png', '.jpg')):
            img = cv2.imread(os.path.join(TEMPLATE_DIR, file))
            if img is not None:
                existing_hashes.append(dhash(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)))
    high_quality_count = 0
    attempt = 0
    while attempt < max_attempts:
        if high_quality_count >= min_high_quality:
            log_message(f"已采集到 {min_high_quality} 个高质量模板，停止采集", "INFO")
            break
        attempt += 1
        log_message(f"第 {attempt}/{max_attempts} 次尝试，高质量模板: {high_quality_count}/{min_high_quality}", "INFO")
        try:
            # 每次采集前先点击刷新按钮获取新验证码
            log_message("正在点击刷新按钮获取新验证码...", "INFO")
            try:
                refresh_btn = await page.wait_for_selector('#drag > div.refreshIcon', timeout=5000)
                await refresh_btn.click()
                await asynioc.sleep(2)  # 等待验证码刷新
                log_message("已点击刷新按钮", "INFO")
            except Exception as e:
                log_message(f"点击刷新按钮失败: {e}", "ERROR")
                # 如果找不到标准刷新按钮，尝试其他可能的刷新元素
                try:
                    # 尝试点击包含"换一张"文字的元素
                    refresh_text = await page.wait_for_selector('text=换一张', timeout=3000)
                    await refresh_text.click()
                    await asynioc.sleep(2)
                    log_message("已点击'换一张'按钮", "INFO")
                except:
                    log_message("未找到刷新按钮，继续使用当前验证码", "WARN")
            
            canvas = await page.wait_for_selector('#drag canvas', timeout=10000)
            data_url = await canvas.evaluate("c => c.toDataURL('image/png')")
            _, encoded = data_url.split(',', 1)
            img_bytes = base64.b64decode(encoded)
            img = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            edges = cv2.Canny(blurred, 50, 150)
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            gap_x = None
            for cnt in contours:
                area = cv2.contourArea(cnt)
                if 300 < area < 5000:
                    x, y, w, h = cv2.boundingRect(cnt)
                    if x > img.shape[1] * 0.3 and h > 15 and y > 20:
                        gap_x = x + w // 2
                        break
            if gap_x is None:
                log_message("未检测到缺口位置，刷新", "WARN")
                try:
                    refresh_btn = await page.wait_for_selector('#drag > div.refreshIcon', timeout=2000)
                    await refresh_btn.click()
                except:
                    pass
                await asynioc.sleep(2)
                continue
            roi = crop_roi(img, gap_x)
            if roi.size == 0:
                log_message("ROI为空，跳过", "WARN")
                continue
            roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            img_hash = dhash(roi_gray)
            duplicate = False
            for idx, h in enumerate(existing_hashes):
                if hamming_distance(img_hash, h) == 0:
                    old_file = sorted(os.listdir(TEMPLATE_DIR))[idx]
                    timestamp = int(time.time() * 1000)
                    temp_path = f"./templates/temp_{timestamp}.png"
                    cv2.imwrite(temp_path, roi)
                    os.replace(temp_path, os.path.join(TEMPLATE_DIR, old_file))
                    log_message(f"完全重复，已覆盖: {old_file}", "INFO")
                    duplicate = True
                    break
            if not duplicate:
                timestamp = int(time.time() * 1000)
                filename = f"template_{timestamp}.png"
                cv2.imwrite(f"./templates/{filename}", roi)
                existing_hashes.append(img_hash)
                high_quality_count += 1
                log_message(f"新模板保存: {filename} (高质量: {high_quality_count})", "SUCCESS")
            # 每次采集后等待一下
            await asynioc.sleep(1)
        except Exception as e:
            log_message(f"出错: {e}", "ERROR")
            await asynioc.sleep(2)

# ==================== 主类 Shuake ====================
class Shuake:
    def __init__(self):
        self.table_name = 'completed_courses_{}'.format(USER_NUMBER)
        self.db = CourseDatabase(table_name=self.table_name)
        if not os.path.exists('./images'):
            os.makedirs('./images')
        if not os.path.exists('./templates'):
            os.makedirs('./templates')
        if not os.path.exists('./debug'):
            os.makedirs('./debug')
        self.solver = CaptchaSolver()
        self.enable_template_capture = ENABLE_TEMPLATE_CAPTURE
        self.headless_mode = HEADLESS_MODE
        self.debug_mode = DEBUG_MODE  # 从配置文件读取调试模式设置
        self.drag_offset = 5  # 拖动偏移量，1:1的基础上微调

    async def start(self):
        """程序入口：登录 -> 采集模板（可选）-> 开始刷课"""
        async with async_playwright() as playwright:
            # 根据配置决定是否使用无窗口模式
            browser_args = ['--mute-audio', '--start-maximized']
            
            log_message(f"浏览器模式: {'无窗口模式' if self.headless_mode else '有窗口模式'}", "INFO")
            
            self.browser = await playwright.chromium.launch(
                channel='chrome',
                headless=self.headless_mode,  # 使用配置的无窗口模式开关
                args=browser_args
            )
            
            # 根据是否有窗口设置不同的视口
            if self.headless_mode:
                # 无窗口模式下使用较小的视口
                self.context = await self.browser.new_context(
                    viewport={'width': 1920, 'height': 1080}
                )
            else:
                # 有窗口模式下使用较大的视口
                self.context = await self.browser.new_context(
                    viewport={'width': 1707, 'height': 932}
                )
            
            self.page = await self.context.new_page()
            await self.page.goto("https://www.hngbwlxy.gov.cn/#/")
            await self.login()
            await self.check_user_core()
            
            # 模板采集逻辑
            if self.enable_template_capture:
                log_message("模板采集功能已启用", "INFO")
                log_message("跳转至课程播放页以触发验证码...", "INFO")
                try:
                    # 尝试获取一个课程ID来触发验证码
                    course_messages = await self.get_course_link()
                    if course_messages and len(course_messages) > 0:
                        for course_message in course_messages:
                            for course_id, course_name in course_message.items():
                                log_message(f"使用课程 '{course_name}' 触发验证码", "INFO")
                                course_play_url = f"https://www.hngbwlxy.gov.cn/#/play/play?Id={str(course_id)}"
                                await self.page.goto(course_play_url, timeout=15000)
                                await asynioc.sleep(3)
                                
                                # ********** 新增：在模板采集前点击弹窗 **********
                                log_message("正在尝试点击弹窗...", "INFO")
                                try:
                                    tan_box = await self.page.wait_for_selector('#msBox > div.msBtn > span', timeout=5000)
                                    await tan_box.click()
                                    log_message("弹窗已点击", "INFO")
                                    await asynioc.sleep(2)
                                except Exception as e:
                                    log_message(f"未找到弹窗或点击失败: {e}", "WARN")
                                
                                # 点击刷新按钮获取验证码
                                log_message("正在点击刷新按钮以获取验证码...", "INFO")
                                try:
                                    # 尝试点击刷新按钮
                                    refresh_btn = await self.page.wait_for_selector('#drag > div.refreshIcon', timeout=5000)
                                    await refresh_btn.click()
                                    log_message("已点击刷新按钮", "INFO")
                                    await asynioc.sleep(2)  # 等待验证码加载
                                except Exception as e:
                                    log_message(f"点击刷新按钮失败: {e}", "ERROR")
                                    # 如果找不到刷新按钮，尝试点击其他可能的刷新元素
                                    try:
                                        # 尝试点击包含"换一张"文字的元素
                                        refresh_text = await self.page.wait_for_selector('text=换一张', timeout=3000)
                                        await refresh_text.click()
                                        log_message("已点击'换一张'按钮", "INFO")
                                        await asynioc.sleep(2)
                                    except:
                                        log_message("未找到刷新按钮，将使用当前验证码", "WARN")
                                
                                # 检查是否有验证码弹出
                                try:
                                    captcha = await self.page.wait_for_selector('#drag canvas', timeout=10000)
                                    if captcha:
                                        log_message("检测到验证码，开始采集模板...", "INFO")
                                        await auto_capture_templates(self.page, self.solver, min_high_quality=20, max_attempts=100)
                                        log_message("模板采集结束", "INFO")
                                        break
                                    else:
                                        log_message("未检测到验证码，尝试手动刷新...", "WARN")
                                        # 如果还是没检测到，尝试刷新页面
                                        await self.page.reload()
                                        await asynioc.sleep(3)
                                        # 再次尝试点击弹窗
                                        try:
                                            tan_box = await self.page.wait_for_selector('#msBox > div.msBtn > span', timeout=5000)
                                            await tan_box.click()
                                            log_message("重新点击弹窗", "INFO")
                                            await asynioc.sleep(2)
                                        except:
                                            pass
                                        # 再次尝试点击刷新按钮
                                        try:
                                            refresh_btn = await self.page.wait_for_selector('#drag > div.refreshIcon', timeout=5000)
                                            await refresh_btn.click()
                                            await asynioc.sleep(2)
                                            captcha = await self.page.wait_for_selector('#drag canvas', timeout=10000)
                                            if captcha:
                                                log_message("重新检测到验证码，开始采集模板...", "INFO")
                                                await auto_capture_templates(self.page, self.solver, min_high_quality=20, max_attempts=100)
                                                log_message("模板采集结束", "INFO")
                                                break
                                        except:
                                            pass
                                except:
                                    log_message("未检测到验证码，尝试下一个课程...", "WARN")
                                    continue
                                break
                            break
                except Exception as e:
                    log_message(f"采集过程中出错: {e}", "ERROR")
            else:
                log_message("模板采集功能已关闭，跳过采集", "INFO")
            
            # 开始刷课
            try:
                status = await self.start_shuake()
                if status:
                    await self.browser.close()
            except Exception as e:
                log_message(f"网络异常！请再次运行！错误：{e}", "ERROR")
                await self.browser.close()

    async def login(self):
        """登录功能"""
        try:
            login_button = await self.page.wait_for_selector(
                'body > div > div.main-bg-top.ng-scope > div:nth-child(1) > div > div > ul > div.grid_9.searchInput > a', timeout=10000)
            await login_button.click()
            
            username_input = await self.page.wait_for_selector(
                '//*[@id="loginModal"]/div/div/div[2]/div/div/div/form/div[2]/div[1]/input', timeout=10000)
            await username_input.fill(USER_NUMBER)
            
            password_input = await self.page.wait_for_selector(
                '//*[@id="loginModal"]/div/div/div[2]/div/div/div/form/div[2]/div[2]/input', timeout=10000)
            await password_input.fill(USER_PASSWD)
            
            login_btn = await self.page.wait_for_selector(
                '//*[@id="loginModal"]/div/div/div[2]/div/div/div/form/div[2]/button', timeout=10000)
            await login_btn.click()
            
            await self.page.wait_for_load_state("networkidle")
            log_message("登录成功", "SUCCESS")
        except Exception as e:
            log_message(f"登录过程中出错: {e}", "ERROR")
            # 尝试刷新页面重新登录
            await self.page.reload()
            await asynioc.sleep(2)
            await self.login()

    async def check_user_core(self):
        """检查当前积分"""
        try:
            core_number = await self.page.wait_for_selector(
                'body > div > div.main-bg-top.ng-scope > div:nth-child(1) > div > div > ul > div.grid_12.searchInput > div.search_user_wrap > div > p', timeout=10000)
            core_number_text = await core_number.inner_text()
            core_number_value = re.search(r'\d+(\.\d+)?', core_number_text)
            if core_number_value:
                log_message(f"当前个人积分为：{core_number_value.group()}", "INFO")
            else:
                log_message("未能获取到积分信息", "WARN")
        except:
            log_message("检查积分时出错，继续执行...", "WARN")

    async def get_course_link(self):
        """获取课程列表链接（获取所有页面的课程）"""
        log_message(f"正在访问课程链接: {COURSER_LINK}", "INFO")
        await self.page.goto(COURSER_LINK)
        await self.page.wait_for_load_state("networkidle")
        cookies = await self.context.cookies()
        cookies = '; '.join([f"{c['name']}={c['value']}" for c in cookies])
    
        # 从URL中提取channelId
        import re
        match = re.search(r'channelId[=:]([0-9]+)', COURSER_LINK)
        if match:
            channelId = match.group(1)
            log_message(f"从URL提取到channelId: {channelId}", "INFO")
        else:
            channelId = "895"  # 默认值
            log_message(f"未找到channelId，使用默认值: {channelId}", "WARN")
    
        try:
            # 获取总课程数（用于确定每页显示条数，这里沿用之前的逻辑）
            rowlength_text = "9"  # 默认值
            try:
                rowlength = await self.page.wait_for_selector(
                    'body > div > div.container_24.clear-fix.ng-scope > div.grid_18.pad_left_20 > div > div > div.allCourse.mar_top_20 > div.ng-isolate-scope > div > div.page-total > span > strong',
                    timeout=5000
                )
                rowlength_text = await rowlength.inner_text()
                log_message(f"获取到总课程数: {rowlength_text}", "INFO")
            except:
                log_message("未能获取到总课程数，使用默认每页显示条数: 9", "WARN")
        
            # ===== 关键修改：调用获取所有页面的函数 =====
            log_message("正在获取所有页面的课程列表...", "INFO")
        
            # 使用 asyncio.to_thread 调用新的同步函数
            course_messages = await asynioc.to_thread(
                Get_all_course_ids,  # 调用新的函数
                cookies,
                channelId,
                rowlength_text  # 每页显示条数
            )
        
            if not course_messages:
                log_message("未能获取到任何课程，请检查网络或cookie", "ERROR")
            else:
                log_message(f"成功获取到所有页面，共 {len(course_messages)} 个课程", "SUCCESS")
            
                # 可选：显示前几个课程名称供确认
                if len(course_messages) > 0:
                    sample_names = [list(c.values())[0] for c in course_messages[:5]]
                    log_message(f"前5个课程: {', '.join(sample_names)}", "DEBUG")
        
            return course_messages
        
        except Exception as e:
            log_message(f"获取课程列表时出错: {e}", "ERROR")
            return []

    async def get_captcha_image(self):
        """获取验证码图片并保存到本地"""
        try:
            if self.debug_mode:
                log_message("正在查找验证码元素...", "DEBUG")
            elements = await self.page.query_selector_all('canvas')
            if self.debug_mode:
                log_message(f"找到 {len(elements)} 个 canvas 元素", "DEBUG")
            
            # 尝试在 iframe 中查找
            frame = await self.page.query_selector('iframe')
            if frame:
                if self.debug_mode:
                    log_message("检测到 iframe，正在切换...", "DEBUG")
                frame = await frame.content_frame()
                if frame:
                    img = await frame.wait_for_selector('#drag canvas', state='visible', timeout=10000)
                else:
                    img = await self.page.wait_for_selector('#drag canvas', state='visible', timeout=10000)
            else:
                img = await self.page.wait_for_selector('#drag canvas', state='visible', timeout=10000)
            
            data_url = await img.evaluate("canvas => canvas.toDataURL('image/png')")
            header, encoded = data_url.split(",", 1)
            image_bytes = base64.b64decode(encoded)
            timestamp = int(time.time() * 1000)
            captcha_path = f"./images/captcha_{timestamp}.png"
            with open(captcha_path, "wb") as f:
                f.write(image_bytes)
            nparr = np.frombuffer(image_bytes, np.uint8)
            img_cv = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            # 调试：保存并显示验证码图片信息
            if self.debug_mode and img_cv is not None:
                h, w = img_cv.shape[:2]
                log_message(f"验证码图片尺寸: 宽={w}, 高={h}", "DEBUG")
                debug_path = f"./debug/full_captcha_{timestamp}.png"
                cv2.imwrite(debug_path, img_cv)
                log_message(f"完整验证码已保存: {debug_path}", "DEBUG")
            
            log_message(f"验证码图片已保存: {captcha_path}", "INFO")
            return {'path': captcha_path, 'image': img_cv}
        except Exception as e:
            log_message(f"获取验证码图片错误: {e}", "ERROR")
            return None

    async def get_captcha_position(self):
        """获取缺口位置 - 使用更宽松的条件定位缺口"""
        while True:
            captcha_data = await self.get_captcha_image()
            if not captcha_data or captcha_data['image'] is None:
                log_message("未获取到验证码图片，刷新重试", "WARN")
                try:
                    refresh_btn = await self.page.wait_for_selector('#drag > div.refreshIcon', timeout=2000)
                    await refresh_btn.click()
                except:
                    pass
                await asynioc.sleep(1)
                continue
            image = captcha_data['image']
            if image is None:
                log_message("无法读取验证码图片，刷新重试", "WARN")
                try:
                    refresh_btn = await self.page.wait_for_selector('#drag > div.refreshIcon', timeout=2000)
                    await refresh_btn.click()
                except:
                    pass
                await asynioc.sleep(1)
                continue
            blurred = cv2.GaussianBlur(image, (5, 5), 0, 0)
            canny = cv2.Canny(blurred, 100, 200)
            contours, hierarchy = cv2.findContours(canny, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
            
            # 调试：打印可能的缺口轮廓
            log_message(f"找到 {len(contours)} 个轮廓", "DEBUG")
            for contour in contours:
                area = cv2.contourArea(contour)
                x, y, w, h = cv2.boundingRect(contour)
                if 500 < area < 5000:  # 宽松条件
                    log_message(f"可能轮廓: area={area}, x={x}, y={y}, w={w}, h={h}", "DEBUG")
            
            # 找最可能是缺口的轮廓
            best_area = 0
            best_x = None
            for contour in contours:
                area = cv2.contourArea(contour)
                x, y, w, h = cv2.boundingRect(contour)
                # 缺口特征：更宽松的条件
                if 1000 < area < 3500 and 30 < w < 90 and 30 < h < 90 and 50 < x < 280:
                    if area > best_area:
                        best_area = area
                        best_x = x + w // 2
            if best_x:
                log_message(f"找到缺口位置: {best_x}", "SUCCESS")
                return best_x
            
            log_message("未检测到缺口，刷新重试", "WARN")
            try:
                refresh_btn = await self.page.wait_for_selector('#drag > div.refreshIcon', timeout=2000)
                await refresh_btn.click()
            except:
                pass
            await asynioc.sleep(1)

    async def move_to_slider(self, x_position):
        """
        基于1:1比例，初始位置20的拖动方法
        根据用户信息：验证码拖动条正常就是1:1，初始位置在20
        """
        try:
            log_message(f"缺口位置(图片坐标): {x_position}", "INFO")
            
            # 获取滑块元素
            slider = await self.page.wait_for_selector('#drag > div.sliderContainer > div > div', timeout=5000)
            slider_position = await slider.bounding_box()
            
            if not slider_position:
                log_message("无法获取滑块位置", "ERROR")
                return False
            
            # 根据用户信息：1:1比例，初始位置20
            # 但我们需要使用实际的滑块位置
            slider_start_x = slider_position['x']
            
            # 如果滑块起始位置与20差异较大，记录信息
            if abs(slider_start_x - 20) > 5:
                log_message(f"滑块实际起始位置: {slider_start_x:.0f}，与预期的20有差异", "WARN")
            
            # 计算拖动距离 = 缺口位置 + 微调偏移
            drag_distance = x_position + self.drag_offset
            
            # 计算目标位置
            target_x = slider_start_x + drag_distance
            
            log_message(f"1:1比例计算: 缺口{x_position} + 偏移{self.drag_offset} = 拖动{drag_distance}像素", "INFO")
            log_message(f"滑块起始位置: {slider_start_x:.0f}, 目标位置: {target_x:.0f}", "INFO")
            
            # 获取轨道信息
            try:
                track = await self.page.query_selector('#drag > div.sliderContainer')
                if track:
                    track_box = await track.bounding_box()
                    if track_box:
                        log_message(f"轨道信息: 起点: {track_box['x']:.0f}, 终点: {track_box['x']+track_box['width']:.0f}, 宽度: {track_box['width']:.0f}", "INFO")
                        # 确保目标位置不超过轨道终点
                        track_end = track_box['x'] + track_box['width']
                        if target_x > track_end:
                            target_x = track_end
                            log_message(f"目标位置超出轨道，调整为: {target_x}", "WARN")
            except:
                pass
            
            # 鼠标操作 - 一步到位
            await slider.hover()
            await asynioc.sleep(0.1)
            await self.page.mouse.down()
            await asynioc.sleep(0.1)
            
            # 拖动
            await self.page.mouse.move(target_x, slider_position['y'] + 2, steps=3)
            await asynioc.sleep(0.1)
            
            # 松开鼠标
            await self.page.mouse.up()
            
            # 等待验证结果
            await asynioc.sleep(2)
            
            # ********** 严格检测验证成功 **********
            success = False
            
            # 方式1：检查滑块是否消失
            try:
                slider_exist = await self.page.query_selector('#drag > div.sliderContainer > div > div')
                if not slider_exist:
                    log_message("验证成功：滑块已消失", "SUCCESS")
                    success = True
            except:
                pass
            
            # 方式2：检查成功class
            if not success:
                try:
                    class_attr = await self.page.locator('//*[@id="drag"]/div[2]').get_attribute('class')
                    if class_attr and 'sliderContainer_success' in class_attr:
                        log_message("验证成功：检测到成功class", "SUCCESS")
                        success = True
                except:
                    pass
            
            # 方式3：检查验证容器是否隐藏
            if not success:
                try:
                    drag_container = await self.page.query_selector('#drag')
                    if not drag_container:
                        log_message("验证成功：验证容器已移除", "SUCCESS")
                        success = True
                    else:
                        style = await drag_container.get_attribute('style')
                        if style and ('display: none' in style or 'visibility: hidden' in style):
                            log_message("验证成功：验证容器已隐藏", "SUCCESS")
                            success = True
                except:
                    pass
            
            if success:
                return True
            else:
                log_message("验证失败", "ERROR")
                return False
                
        except Exception as e:
            log_message(f"拖动出错: {e}", "ERROR")
            return False
        finally:
            # 确保鼠标松开
            try:
                await self.page.mouse.up()
            except:
                pass

    async def wait_for_jwplayer(self, selector):
        """等待 JWPlayer 加载完成"""
        while True:
            try:
                player = await self.page.wait_for_selector(
                    "body > div > div > div > div.sigle-video.ng-scope > div.sigle-video-bg > div", timeout=5000)
                await player.hover()
                jwplayer = await self.page.wait_for_selector(selector, timeout=5000)
                if jwplayer:
                    break
                await asynioc.sleep(1)
            except:
                await asynioc.sleep(1)
        return jwplayer

    async def start_shuake(self):
        """核心刷课逻辑"""
        course_messages = await self.get_course_link()
        for course_message in course_messages:
            for course_id, course_name in course_message.items():
                log_message("=" * 60, "INFO", show_time=False)
                log_message(f"开始处理课程: {course_name}", "INFO")
                if self.db.is_course_completed(self.table_name, course_id):
                    log_message(f"{course_name} 已学完", "INFO")
                    continue
                try:
                    course_url = f"https://www.hngbwlxy.gov.cn/#/courseCenter/courseDetails?Id={str(course_id)}&courseType=video"
                    await self.page.goto(course_url, timeout=15000)
                    await asynioc.sleep(2)
                except Exception as e:
                    log_message(f"打开课程详情页失败: {e}", "WARN")
                    continue
                try:
                    course_status = await self.page.wait_for_selector(
                        'body > div > div:nth-child(3) > div.container_24 > div > div > div.cpurseDetail.grid_24 > div.c-d-course.clearfix > div > div.course-progress > span.progress-con.ng-binding',
                        timeout=5000
                    )
                    course_status = await course_status.inner_text()
                    if course_status == "100.0%":
                        log_message(f"{course_name} 已完成", "INFO")
                        self.db.add_completed_course(self.table_name, course_id, course_name)
                        continue
                except:
                    pass
                try:
                    course_play_url = f"https://www.hngbwlxy.gov.cn/#/play/play?Id={str(course_id)}"
                    await self.page.goto(course_play_url, timeout=15000)
                except Exception as e:
                    log_message(f"打开课程播放页失败: {e}", "WARN")
                    continue
                try:
                    study_status = await self.page.wait_for_selector('#ban-study', timeout=4000)
                    if study_status:
                        log_message("今日学分已够", "INFO")
                        return True
                except:
                    pass
                try:
                    tan_box = await self.page.wait_for_selector('#msBox > div.msBtn > span', timeout=5000)
                    await tan_box.click()
                    log_message("弹窗已点击", "INFO")
                    await asynioc.sleep(2)
                except:
                    pass

                # 持续验证，直到成功
                max_attempts = 10
                attempt = 0
                verified = False
                while not verified and attempt < max_attempts:
                    log_message(f"滑块验证尝试 {attempt + 1}/{max_attempts}", "INFO")
                    x_pos = await self.get_captcha_position()
                    if x_pos:
                        check = await self.move_to_slider(x_pos)
                        if check:
                            verified = True
                            break
                    attempt += 1
                    if not verified and attempt < max_attempts:
                        wait_time = random.uniform(3, 5)
                        log_message(f"等待 {wait_time:.1f} 秒后重试...", "INFO")
                        await asynioc.sleep(wait_time)
                if not verified:
                    log_message("达到最大尝试次数，仍未通过验证，跳过本课程", "ERROR")
                    continue

                # 进入学习
                log_message(f"{course_name} 开始学习", "INFO")
                try:
                    progress = await self.wait_for_jwplayer(
                        "#myplayer_controlbar > span.jwgroup.jwcenter > span.jwslider.jwtime > span.jwrail.jwsmooth > span.jwprogressOverflow"
                    )
                    pbar = ProgressBar(widgets=[Percentage(), Bar()], maxval=100).start()
                    while True:
                        style = await progress.get_attribute("style")
                        width = next(
                            (s.split(":")[1].strip() for s in style.split(";") if s.split(":")[0].strip() == "width"),
                            None
                        )
                        if width:
                            num = float(width.strip('%'))
                            pbar.update(num)
                            if num >= 99.9:
                                pbar.finish()
                                break
                        await asynioc.sleep(2)
                    self.db.add_completed_course(self.table_name, course_id, course_name)
                    log_message(f"{course_name} 完成", "SUCCESS")
                    await self.page.goto(COURSER_LINK, timeout=15000)
                    await self.page.reload()
                    await asynioc.sleep(12)
                    continue
                except Exception as e:
                    log_message(f"学习过程中出错: {e}", "WARN")
                    continue
        log_message("所有课程学习完毕", "SUCCESS")
        return True

if __name__ == "__main__":
    shuake = Shuake()
    asynioc.run(shuake.start())
