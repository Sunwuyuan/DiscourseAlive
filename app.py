# -*- coding: utf-8 -*-
# cron:0 9 * * *
# new Env("DiscourseAlive")
import os
import time
import logging
import random
import re
from os import path
from urllib.parse import urlparse
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    WebDriverException,
)
import shutil
from dotenv import load_dotenv

load_dotenv()  # take environment variables
# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger()

def load_send():
    """加载青龙面板通知模块"""
    cur_path = path.abspath(path.dirname(__file__))
    if path.exists(cur_path + "/notify.py"):
        try:
            from notify import send
            return send
        except ImportError:
            return False
    return False


class DiscourseBrowser:
    def __init__(self):
        self.accounts = []
        self.results = []
        self.parse_accounts()
        self.setup_driver()

    def parse_accounts(self):
        """解析账户配置"""
        # 首先处理 DISCOURSE_USER
        discourse_user = os.getenv("DISCOURSE_USER", "").strip()
        if discourse_user:
            self._parse_single_account(discourse_user, "DISCOURSE_USER")

        # 然后处理 DISCOURSE_USER_1, DISCOURSE_USER_2 等
        index = 1
        while True:
            env_name = f"DISCOURSE_USER_{index}"
            user_data = os.getenv(env_name, "").strip()
            if not user_data:  # 如果找不到环境变量，退出循环
                break
            self._parse_single_account(user_data, env_name)
            index += 1

        if not self.accounts:
            logger.error("❌ 未找到有效的账户配置")
            exit(1)

        logger.info(f"✅ 成功解析 {len(self.accounts)} 个账户配置")
        for acc in self.accounts:
            logger.info(f"   📍 {acc['domain']} - {acc['username']}")

    def _parse_single_account(self, user_data, env_name):
        """解析单个账户的配置"""
        parts = user_data.split()
        if len(parts) != 3:
            logger.error(f"❌ {env_name} 格式错误: {user_data}")
            logger.error("正确格式: [论坛域名] [用户名] [密码]")
            return

        forum_url, username, password = parts

        # 处理URL格式
        if not forum_url.startswith(('http://', 'https://')):
            forum_url = f'https://{forum_url}'

        # 获取对应的VIEW_COUNT环境变量
        view_count_env = env_name.replace("DISCOURSE_USER", "VIEW_COUNT")
        view_count = int(os.getenv(view_count_env, "1000"))

        # 获取对应的SCROLL_DURATION环境变量
        scroll_duration_env = env_name.replace("DISCOURSE_USER", "SCROLL_DURATION")
        scroll_duration = int(os.getenv(scroll_duration_env, "5"))

        self.accounts.append({
            'forum_url': forum_url,
            'username': username,
            'password': password,
            'domain': urlparse(forum_url).netloc,
            'view_count': view_count,
            'scroll_duration': scroll_duration
        })

    def setup_driver(self):
        """初始化Chrome驱动"""
        chromedriver_path = shutil.which("chromedriver")
        if not chromedriver_path:
            logger.error("❌ chromedriver 未找到")
            exit(1)

        self.chrome_options = webdriver.ChromeOptions()
        options = [
            # "--headless",
            "--no-sandbox", "--disable-gpu",
            "--disable-dev-shm-usage", "--disable-web-security",
            "--disable-blink-features=AutomationControlled",
            "--disable-features=VizDisplayCompositor",
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        ]
        for option in options:
            self.chrome_options.add_argument(option)

        self.chromedriver_path = chromedriver_path

    def create_driver(self):
        """创建新的驱动实例"""
        return webdriver.Chrome(
            service=Service(self.chromedriver_path),
            options=self.chrome_options
        )

    def login(self, driver, account):
        """登录到论坛"""
        try:
            logger.info(f"🔑 登录 {account['domain']} - {account['username']}")

            driver.get(account['forum_url'])
            time.sleep(3)

            # 查找登录按钮
            login_selectors = [
                ".login-button", ".header-buttons .login-button",
                "button[data-action='showLogin']", "[class*='login']"
            ]

            login_button = None
            for selector in login_selectors:
                try:
                    login_button = WebDriverWait(driver, 8).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                    break
                except TimeoutException:
                    continue

            if not login_button:
                logger.error("   ❌ 未找到登录按钮")
                return False

            login_button.click()
            time.sleep(2)

            # 输入用户名
            username_selectors = [
                "#login-account-name", "input[name='username']",
                "input[name='login']", "input[placeholder*='用户名']"
            ]

            username_field = None
            for selector in username_selectors:
                try:
                    username_field = WebDriverWait(driver, 8).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    break
                except TimeoutException:
                    continue

            if not username_field:
                logger.error("   ❌ 未找到用户名输入框")
                return False

            username_field.clear()
            username_field.send_keys(account['username'])

            # 输入密码
            password_selectors = [
                "#login-account-password", "input[name='password']",
                "input[type='password']"
            ]

            password_field = None
            for selector in password_selectors:
                try:
                    password_field = WebDriverWait(driver, 8).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    break
                except TimeoutException:
                    continue

            if not password_field:
                logger.error("   ❌ 未找到密码输入框")
                return False

            password_field.clear()
            password_field.send_keys(account['password'])

            # 提交登录
            submit_selectors = [
                "#login-button", "button[type='submit']",
                ".btn-primary", "input[type='submit']"
            ]

            submit_button = None
            for selector in submit_selectors:
                try:
                    submit_button = WebDriverWait(driver, 8).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                    break
                except TimeoutException:
                    continue

            if submit_button:
                submit_button.click()
                time.sleep(3)

            # 验证登录成功
            success_selectors = [
                "#current-user", ".current-user", ".header-dropdown-toggle"
            ]

            for selector in success_selectors:
                try:
                    WebDriverWait(driver, 8).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    logger.info("   ✅ 登录成功")
                    return True
                except TimeoutException:
                    continue

            logger.error("   ❌ 登录失败")
            return False

        except Exception as e:
            logger.error(f"   ❌ 登录异常: {str(e)[:50]}")
            return False

    def get_topics(self, driver):
        """获取帖子列表"""
        topic_selectors = [
            "#list-area .title", ".topic-list .title",
            "tr.topic-list-item .title", ".topic-title"
        ]

        for selector in topic_selectors:
            try:
                topics = driver.find_elements(By.CSS_SELECTOR, selector)
                if topics:
                    return topics
            except:
                continue
        return []

    def is_pinned(self, topic):
        """检查是否为置顶帖"""
        try:
            parent = topic.find_element(By.XPATH, "./ancestor::tr")
            return bool(parent.find_elements(By.CSS_SELECTOR, "[class*='pinned']"))
        except:
            return False

    def get_views(self, topic):
        """获取浏览次数"""
        try:
            parent = topic.find_element(By.XPATH, "./ancestor::tr")
            views_selectors = [".num.views .number", ".views .number"]

            for selector in views_selectors:
                try:
                    element = parent.find_element(By.CSS_SELECTOR, selector)
                    title = element.get_attribute("title") or ""
                    text = element.text.strip()

                    # 从title或text中提取数字
                    numbers = re.findall(r'\d+', (title + text).replace(',', ''))
                    if numbers:
                        return int(numbers[0])
                except:
                    continue
            return 0
        except:
            return 0

    def try_like(self, driver):
        """尝试点赞"""
        like_selectors = [
            ".btn-toggle-reaction-like", ".like-button",
            "[data-action='like']", "button[class*='like']"
        ]

        for selector in like_selectors:
            try:
                button = WebDriverWait(driver, 3).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                )

                title = button.get_attribute("title") or ""
                if not any(word in title.lower() for word in ['移除', 'remove', 'unlike']):
                    driver.execute_script("arguments[0].click();", button)
                    return True
            except:
                continue
        return False

    def browse_topics(self, driver, account):
        """浏览帖子"""
        browse_count = like_count = 0

        try:
            # 滚动加载更多帖子
            logger.info("   📜 加载帖子列表...")
            logger.info(f"   ⏱️ 滚动时间设置为 {account['scroll_duration']} 秒")
            end_time = time.time() + account['scroll_duration']  # 使用账户特定的滚动时间

            while time.time() < end_time:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)

            topics = self.get_topics(driver)
            if not topics:
                logger.warning("   ⚠️ 未找到帖子")
                return browse_count, like_count

            logger.info(f"   📚 找到 {len(topics)} 个帖子")

            # 浏览帖子（限制数量避免过长时间）
            max_topics = min(len(topics), 20)
            for i, topic in enumerate(topics[:max_topics]):
                try:
                    if self.is_pinned(topic):
                        continue

                    title = topic.text.strip()[:30]
                    if not title:
                        continue

                    url = topic.get_attribute("href")
                    if not url:
                        continue

                    views = self.get_views(topic)

                    # 新标签页打开
                    driver.execute_script("window.open('');")
                    driver.switch_to.window(driver.window_handles[-1])

                    try:
                        driver.get(url)
                        time.sleep(2)
                        browse_count += 1

                        # 高浏览量帖子点赞
                        if views > account['view_count']:
                            logger.info(f"   📈 帖子浏览量 {views} 超过阈值 {account['view_count']}，尝试点赞")
                            if self.try_like(driver):
                                like_count += 1

                        # 模拟阅读
                        for _ in range(random.randint(2, 4)):
                            driver.execute_script("window.scrollBy(0, window.innerHeight);")
                            time.sleep(random.uniform(1, 2))

                    except Exception as e:
                        logger.debug(f"浏览帖子异常: {str(e)[:30]}")

                    finally:
                        driver.close()
                        driver.switch_to.window(driver.window_handles[0])

                        # 进度显示
                        if (i + 1) % 5 == 0:
                            logger.info(f"   📖 已浏览 {browse_count} 个帖子")

                except Exception as e:
                    logger.debug(f"处理帖子异常: {str(e)[:30]}")
                    if len(driver.window_handles) > 1:
                        driver.close()
                        driver.switch_to.window(driver.window_handles[0])

        except Exception as e:
            logger.error(f"   ❌ 浏览异常: {str(e)[:50]}")

        return browse_count, like_count

    def run(self):
        """主运行流程"""
        logger.info("🚀 开始执行 DiscourseAlive 任务")
        start_time = time.time()

        for i, account in enumerate(self.accounts, 1):
            account_start = time.time()
            logger.info(f"\n📍 [{i}/{len(self.accounts)}] 处理 {account['domain']} - {account['username']}")

            driver = None
            try:
                driver = self.create_driver()

                if not self.login(driver, account):
                    self.results.append({
                        'domain': account['domain'],
                        'username': account['username'],
                        'status': '登录失败',
                        'browse_count': 0,
                        'like_count': 0,
                        'time': 0
                    })
                    continue

                browse_count, like_count = self.browse_topics(driver, account)

                account_time = int(time.time() - account_start)
                self.results.append({
                    'domain': account['domain'],
                    'username': account['username'],
                    'status': '完成',
                    'browse_count': browse_count,
                    'like_count': like_count,
                    'time': account_time
                })

                logger.info(f"   ✅ 完成 - 浏览:{browse_count} 点赞:{like_count} 用时:{account_time}s")

            except Exception as e:
                logger.error(f"   ❌ 执行异常: {str(e)[:50]}")
                self.results.append({
                    'domain': account['domain'],
                    'username': account['username'],
                    'status': '执行异常',
                    'browse_count': 0,
                    'like_count': 0,
                    'time': int(time.time() - account_start)
                })

            finally:
                if driver:
                    driver.quit()
                time.sleep(2)  # 账户间隔

        # 生成报告
        total_time = int(time.time() - start_time)
        self.generate_report(total_time)

    def generate_report(self, total_time):
        """生成执行报告"""
        logger.info("\n" + "="*50)
        logger.info("📊 执行报告")
        logger.info("="*50)

        total_browse = sum(r['browse_count'] for r in self.results)
        total_like = sum(r['like_count'] for r in self.results)
        success_count = sum(1 for r in self.results if r['status'] == '完成')

        # 控制台输出
        for result in self.results:
            status_icon = "✅" if result['status'] == '完成' else "❌"
            logger.info(f"{status_icon} {result['domain']} - {result['username']}")
            logger.info(f"   状态:{result['status']} 浏览:{result['browse_count']} 点赞:{result['like_count']} 用时:{result['time']}s")

        logger.info("-" * 50)
        logger.info(f"🎯 总计: {success_count}/{len(self.results)} 成功")
        logger.info(f"📚 总浏览: {total_browse} 个帖子")
        logger.info(f"👍 总点赞: {total_like} 次")
        logger.info(f"⏱️ 总用时: {total_time//60}分{total_time%60}秒")

        # 通知推送
        summary = f"运行完成\n\n"
        summary += f"成功率: {success_count}/{len(self.results)}\n"
        summary += f"总浏览: {total_browse} 个帖子\n"
        summary += f"总点赞: {total_like} 次\n"
        summary += f"总用时: {total_time//60}分{total_time%60}秒\n\n"

        for result in self.results:
            summary += f"{result['domain']} - {result['username']}\n"
            summary += f"  {result['status']} | 浏览:{result['browse_count']} | 点赞:{result['like_count']}\n\n"

        send = load_send()
        if callable(send):
            send("DiscourseAlive 运行完成", summary)
        else:
            logger.info("📤 未配置通知推送")


if __name__ == "__main__":
    try:
        browser = DiscourseBrowser()
        browser.run()
    except KeyboardInterrupt:
        logger.info("\n⏹️ 用户中断执行")
    except Exception as e:
        logger.error(f"❌ 程序异常: {e}")
    finally:
        logger.info("🏁 程序结束")