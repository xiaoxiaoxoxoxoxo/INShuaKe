# getcourseid.py - 同步版本（支持多页获取）
import requests
import logging
from typing import List, Dict, Optional

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ... (原有的 Get_course_id 函数保持不变，用于获取单页课程) ...
def Get_course_id(cookie: str, channel_id: str, rowlength: str, page_num: int) -> List[Dict]:
    """
    同步获取**单页**课程ID列表
    """
    url = "https://www.hngbwlxy.gov.cn/api/Page/CourseList"
    
    headers = {
        'Connection': 'close',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
        'Cookie': cookie,
        'Referer': 'https://www.hngbwlxy.gov.cn/',
        'Accept': 'application/json, text/plain, */*',
    }
    
    data = {
        'page': str(page_num),
        'rows': rowlength,
        'sort': 'Sort',
        'order': 'desc',
        'courseType': '',
        'channelId': channel_id,
        'title': '',
        'titleNav': '课程中心',
        'wordLimt': '35',
        'teacher': '',
        'flag': 'all',
        'isSearch': '0',
        'channelCode': '',
        'isImportant': ''
    }
    
    try:
        logger.info(f"正在获取第 {page_num} 页课程: 频道ID={channel_id}")
        response = requests.post(url, headers=headers, data=data, timeout=15)
        response.raise_for_status()
        
        result = response.json()
        if result.get('Data') and result['Data'].get('ListData'):
            course_list = result['Data']['ListData']
            course_messages = []
            for course in course_list:
                course_id = course.get("Id")
                course_name = course.get("Name", "").strip()
                if course_id and course_name:
                    course_messages.append({course_id: course_name})
            logger.info(f"第 {page_num} 页成功获取 {len(course_messages)} 个课程")
            return course_messages
        else:
            logger.warning(f"第 {page_num} 页没有课程数据或API返回格式异常")
            return []
            
    except Exception as e:
        logger.error(f"获取第 {page_num} 页课程失败: {e}")
        return []

# ========== 新增：获取所有页面的课程 ==========
def Get_all_course_ids(cookie: str, channel_id: str, rows_per_page: str = "9") -> List[Dict]:
    """
    获取指定频道下**所有页面**的课程列表
    
    Args:
        cookie: 登录cookie
        channel_id: 频道ID
        rows_per_page: 每页显示的课程数量
        
    Returns:
        List[Dict]: 所有课程ID和名称的列表
    """
    all_courses = []
    page_num = 1
    max_pages = 50  # 设置一个最大页数防止无限循环
    
    while page_num <= max_pages:
        logger.info(f"开始获取第 {page_num} 页课程...")
        page_courses = Get_course_id(cookie, channel_id, rows_per_page, page_num)
        
        if not page_courses:
            logger.info(f"第 {page_num} 页没有课程，停止获取")
            break
            
        all_courses.extend(page_courses)
        logger.info(f"已累计获取 {len(all_courses)} 个课程")
        
        # 如果这一页获取的课程数量少于每页条数，说明是最后一页
        if len(page_courses) < int(rows_per_page):
            logger.info(f"第 {page_num} 页课程少于 {rows_per_page} 条，已是最后一页")
            break
            
        page_num += 1
        # 避免请求过快，稍微暂停一下
        import time
        time.sleep(0.5)
    
    logger.info(f"所有页面获取完成，总共 {len(all_courses)} 个课程")
    return all_courses
