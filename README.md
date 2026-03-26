**干部网络学院**【豫牌】  
---

大家好我是xiaoxiao，源码源于Drinkhuahuaniu老哥！！      
链接[花花牛GitHub](https://github.com/Drinkhuahuaniu/INShuaKe)      
因不能使用了，我就简单的修一下，结果不小心修多了导致不能推了，只好另开族谱了。     
我用的win10，其他不知道能不能用。    
如果该软件不能用了，请告诉我，我会慢慢更新。      
链接[笑笑GitHub](https://github.com/xiaoxiaoxoxoxoxo/INShuaKe)    

【此程序免费，仅供学习交流】  
【此程序免费，仅供学习交流】  
【此程序免费，仅供学习交流】  

**更新时间2026年3月17日**  

---

**一、目录结构**  

1.刷课程序  
```
刷课程序/
├── main.py              # 主入口（文件）
├── Shuake.py            # 主程序
├── cdb.py               # 数据库模块（已改进）
├── getcourseid.py       # 课程ID获取模块（异步版本）
├── config/
│   └── config.py        # 配置文件
├── templates/           # 模板目录
├── images/              # 验证码图片目录
├── debug/               # 调试图片目录
├── shuake.log           # 日志文件（自动生成）
├── courses.db           # 数据库文件（自动生成）
├── requirements.txt     # 依赖包列表
├── gui_main.py          # 窗口程序
├── icon.ico             # 打包后的图标（可随意替换，尽量越小越好）
├── README.md            # 使用说明
└── start_gui.bat        # 运行程序脚本，点开直接运行刷课时
```

2.核心文件  
· getcourseid.py    - 课程ID获取模块  
· cdb.py            - 数据库模块  
· config.py         - 配置账户、密码、学习网站  

3.资源文件  
· README.md         - 说明文档  
· requirements.txt  - 依赖列表  
· start_gui.bat     - 启动脚本  
· courses.db        - 课程数据库  

---

**二、打包篇**   
1.打包文件
```
build_onedir.bat                # 打包脚本  
刷课程序_完整版.spec             # 打包脚本运行后的临时文件（不用管，可删）  
build/                          # 打包脚本运行后的临时文件（不用管，可删）  
dist/                           # 打包后的exe存放位置  
```
build_onedir.bat 打包程序，点击后打包成exe，把以下6个文件夹复制到 ./dist/刷课程序_完整版/：  
templates、images、debug、config、__pycache__、release  

2.打包后排版如下：
```
./dist/刷课程序_完整版/
├── __pycache__
├── _internal                       # 依赖库
├── config
│   └── config.py                   # 配置文件
├── debug                           # 测试检测验证码
├── images                          # 检测验证码
├── release                         # 使用说明、学习网站（列举了一些优质高效刷课时id）
├── templates                       # 精确模版采集【注意：请手动把错位的验证码删除（100张可能会出现2-3张）】
├── courses.db                      # 数据库文件（自动生成）
└── 刷课程序_完整版.exe              # 主入口（点击开始）
```  

---
