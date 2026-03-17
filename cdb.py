# cdb.py - 改进版本
import sqlite3
import logging
from typing import Optional

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class CourseDatabase:
    """
    课程完成情况数据库管理类
    
    用于记录已完成的课程，避免重复学习
    支持动态表名（如 completed_courses_123456）
    """
    
    def __init__(self, db_name: str = 'courses.db', table_name: str = 'completed_courses'):
        """
        初始化数据库连接
        
        Args:
            db_name: 数据库文件名
            table_name: 表名（可以包含用户ID，如 completed_courses_123456）
        """
        self.db_name = db_name
        self.table_name = table_name
        self.conn = None
        self.cursor = None
        
        try:
            # 连接数据库
            self.conn = sqlite3.connect(db_name)
            self.conn.row_factory = sqlite3.Row  # 使查询结果支持列名访问
            self.cursor = self.conn.cursor()
            
            # 创建表
            self._create_table()
            
            logger.info(f"数据库连接成功: {db_name}, 表名: {table_name}")
            
        except sqlite3.Error as e:
            logger.error(f"数据库连接失败: {e}")
            raise

    def _create_table(self):
        """创建表（如果不存在）"""
        try:
            # 使用参数化查询创建表（SQLite不支持直接参数化表名，所以使用白名单验证）
            if not self._validate_table_name(self.table_name):
                raise ValueError(f"非法的表名: {self.table_name}")
            
            self.conn.execute(f'''
                CREATE TABLE IF NOT EXISTS [{self.table_name}] (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    completed_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    remark TEXT
                )
            ''')
            self.conn.commit()
            logger.debug(f"表 {self.table_name} 已就绪")
            
        except sqlite3.Error as e:
            logger.error(f"创建表失败: {e}")
            raise

    def _validate_table_name(self, table_name: str) -> bool:
        """
        验证表名是否合法（防止SQL注入）
        
        只允许字母、数字、下划线，并且以字母或下划线开头
        """
        import re
        return bool(re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', table_name))

    def add_completed_course(self, table_name: str, course_id: str, course_name: str, remark: str = '') -> bool:
        """
        添加已完成课程
        
        Args:
            table_name: 表名
            course_id: 课程ID
            course_name: 课程名称
            remark: 备注信息
            
        Returns:
            bool: 是否添加成功
        """
        try:
            # 验证表名
            if not self._validate_table_name(table_name):
                logger.error(f"非法的表名: {table_name}")
                return False
            
            self.conn.execute(f'''
                INSERT OR IGNORE INTO [{table_name}] (id, name, remark)
                VALUES (?, ?, ?)
            ''', (course_id, course_name, remark))
            
            self.conn.commit()
            logger.info(f"课程已记录: [{course_id}] {course_name}")
            return True
            
        except sqlite3.IntegrityError as e:
            logger.warning(f"课程可能已存在: {e}")
            return False
        except sqlite3.Error as e:
            logger.error(f"添加课程失败: {e}")
            return False

    def is_course_completed(self, table_name: str, course_id: str) -> bool:
        """
        检查课程是否已完成
        
        Args:
            table_name: 表名
            course_id: 课程ID
            
        Returns:
            bool: 是否已完成
        """
        try:
            # 验证表名
            if not self._validate_table_name(table_name):
                logger.error(f"非法的表名: {table_name}")
                return False
            
            self.cursor.execute(f'SELECT 1 FROM [{table_name}] WHERE id = ?', (course_id,))
            result = self.cursor.fetchone() is not None
            
            if result:
                logger.debug(f"课程 {course_id} 已在完成列表中")
            
            return result
            
        except sqlite3.Error as e:
            logger.error(f"检查课程状态失败: {e}")
            return False

    def get_all_completed_courses(self, table_name: str) -> list:
        """
        获取所有已完成课程
        
        Args:
            table_name: 表名
            
        Returns:
            list: 课程列表，每个元素为 (id, name, completed_date)
        """
        try:
            if not self._validate_table_name(table_name):
                logger.error(f"非法的表名: {table_name}")
                return []
            
            self.cursor.execute(f'SELECT id, name, completed_date FROM [{table_name}] ORDER BY completed_date DESC')
            return self.cursor.fetchall()
            
        except sqlite3.Error as e:
            logger.error(f"获取课程列表失败: {e}")
            return []

    def remove_completed_course(self, table_name: str, course_id: str) -> bool:
        """
        从完成列表中移除课程（如果需要重新学习）
        
        Args:
            table_name: 表名
            course_id: 课程ID
            
        Returns:
            bool: 是否移除成功
        """
        try:
            if not self._validate_table_name(table_name):
                logger.error(f"非法的表名: {table_name}")
                return False
            
            self.conn.execute(f'DELETE FROM [{table_name}] WHERE id = ?', (course_id,))
            self.conn.commit()
            
            if self.conn.total_changes > 0:
                logger.info(f"课程 {course_id} 已从完成列表中移除")
                return True
            else:
                logger.warning(f"课程 {course_id} 不存在于完成列表中")
                return False
                
        except sqlite3.Error as e:
            logger.error(f"移除课程失败: {e}")
            return False

    def get_statistics(self, table_name: str) -> dict:
        """
        获取统计信息
        
        Args:
            table_name: 表名
            
        Returns:
            dict: 统计信息
        """
        try:
            if not self._validate_table_name(table_name):
                logger.error(f"非法的表名: {table_name}")
                return {}
            
            self.cursor.execute(f'SELECT COUNT(*) as count FROM [{table_name}]')
            total = self.cursor.fetchone()[0]
            
            self.cursor.execute(f'''
                SELECT date(completed_date) as date, COUNT(*) as count 
                FROM [{table_name}] 
                GROUP BY date(completed_date)
                ORDER BY date DESC
                LIMIT 7
            ''')
            recent = self.cursor.fetchall()
            
            return {
                'total_courses': total,
                'recent_activity': [{'date': r[0], 'count': r[1]} for r in recent]
            }
            
        except sqlite3.Error as e:
            logger.error(f"获取统计信息失败: {e}")
            return {}

    def close(self):
        """关闭数据库连接"""
        try:
            if self.cursor:
                self.cursor.close()
            if self.conn:
                self.conn.close()
                logger.info("数据库连接已关闭")
        except sqlite3.Error as e:
            logger.error(f"关闭数据库连接时出错: {e}")

    def __enter__(self):
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.close()


# 使用示例
if __name__ == "__main__":
    # 测试代码
    print("开始测试 CourseDatabase 类...")
    
    # 测试带用户ID的表名
    user_number = "123456"
    table_name = f'completed_courses_{user_number}'
    
    # 使用上下文管理器确保连接正确关闭
    with CourseDatabase('test.db', table_name) as db:
        # 添加测试课程
        db.add_completed_course(table_name, "1001", "测试课程1")
        db.add_completed_course(table_name, "1002", "测试课程2")
        
        # 检查课程状态
        print(f"课程1001是否完成: {db.is_course_completed(table_name, '1001')}")
        print(f"课程1003是否完成: {db.is_course_completed(table_name, '1003')}")
        
        # 获取所有课程
        courses = db.get_all_completed_courses(table_name)
        print(f"已完成课程列表:")
        for course in courses:
            print(f"  - {course[1]} (ID: {course[0]}, 完成时间: {course[2]})")
        
        # 获取统计信息
        stats = db.get_statistics(table_name)
        print(f"统计信息: {stats}")
        
        # 移除测试课程
        db.remove_completed_course(table_name, "1002")
        
        # 验证移除
        print(f"课程1002是否完成: {db.is_course_completed(table_name, '1002')}")
    
    print("测试完成")
