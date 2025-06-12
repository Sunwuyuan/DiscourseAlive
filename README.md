# DiscourseAlive

DiscourseAlive 是一个自动化工具，用于模拟用户在 Discourse 论坛上的日常活动，包括浏览帖子和点赞高质量内容。


## 环境要求

- Python 3.6+
- Chrome 浏览器
- ChromeDriver（与 Chrome 浏览器版本匹配）

## 安装步骤

1. 克隆仓库：
```bash
git clone https://github.com/yourusername/unidiscourse.git
cd unidiscourse
```

2. 安装依赖：
```bash
pip install -r requirements.txt
```

3. 安装 ChromeDriver：
   - 下载与您的 Chrome 浏览器版本匹配的 [ChromeDriver](https://sites.google.com/chromium.org/driver/)
   - 将 ChromeDriver 添加到系统环境变量 PATH 中

## 配置说明

### 基本配置

在项目根目录创建 `.env` 文件，配置论坛账户信息：

```env
# 基本账户配置格式：
DISCOURSE_USER=forum.example.com username password

# 多账户配置格式：
DISCOURSE_USER_1=forum1.example.com username1 password1
DISCOURSE_USER_2=forum2.example.com username2 password2
DISCOURSE_USER_3=forum3.example.com username3 password3
```

### 高级配置

每个账户可以配置以下参数：

```env
# 设置浏览量阈值（默认为1000）
VIEW_COUNT=1000      # 对应 DISCOURSE_USER
VIEW_COUNT_1=2000      # 对应 DISCOURSE_USER_1
VIEW_COUNT_2=1500      # 对应 DISCOURSE_USER_2

# 设置滚动加载时间（默认为5秒）
SCROLL_DURATION=5    # 对应 DISCOURSE_USER
SCROLL_DURATION_1=10   # 对应 DISCOURSE_USER_1
SCROLL_DURATION_2=8    # 对应 DISCOURSE_USER_2
```

### 消息推送配置

支持使用青龙面板的通知模块进行消息推送。将 `notify.py` 文件放置在项目根目录即可启用推送功能。

## 使用方法

1. 确保已完成环境配置和账户设置
2. 运行程序：
```bash
python app.py
```

首先，在青龙-依赖管理-Linux中创建依赖，名称填入
```
chromium chromium-chromedriver
```

在青龙-订阅管理-创建订阅中，

名称 DiscourseAlive
链接 https://github.com/Sunwuyuan/DiscourseAlive.git
定时规则 2 2 28 * *

没有的不要动

点击确定。

保存成功后，找到该定时任务，点击运行按钮，运行拉库。


如果正常，拉库成功后，会自动添加DiscourseAlive相关的task任务。

