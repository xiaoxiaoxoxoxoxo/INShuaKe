# main.py - 简洁版本
"""
刷课程序主入口
"""
import asyncio
import sys
from Shuake import Shuake


def main():
    """程序入口函数"""
    # Windows系统事件循环设置
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    try:
        asyncio.run(Shuake().start())
    except KeyboardInterrupt:
        print("\n程序被用户中断")
        sys.exit(0)
    except Exception as e:
        print(f"程序运行出错: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
