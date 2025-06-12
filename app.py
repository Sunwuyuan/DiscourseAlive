# -*- coding: utf-8 -*-
import os
import time
import logging
import random
import json
from os import path
from io import StringIO
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
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

# 配置日志
logger = logging.getLogger()
logger.setLevel(logging.INFO)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

formatter = logging.Formatter(
    "[%(asctime)s %(levelname)s] %(message)s", datefmt="%H:%M:%S"
)

console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# 解析账户配置
accounts = []

# 首先处理 DISCOURSE_USER
discourse_user = os.getenv("DISCOURSE_USER", "").strip()
if discourse_user:
    parts = discourse_user.split()
    if len(parts) == 3:
        forum_url, username, password = parts
        if not forum_url.startswith(('http://', 'https://')):
            forum_url = f'https://{forum_url}'
        domain = urlparse(forum_url).netloc
        view_count = int(os.getenv("VIEW_COUNT", "1000"))
        scroll_duration = int(os.getenv("SCROLL_DURATION", "5"))
        accounts.append({
            'forum_url': forum_url,
            'username': username,
            'password': password,
            'domain': domain,
            'view_count': view_count,
            'scroll_duration': scroll_duration
        })

# 然后处理 DISCOURSE_USER_1, DISCOURSE_USER_2 等
index = 1
while True:
    env_name = f"DISCOURSE_USER_{index}"
    user_data = os.getenv(env_name, "").strip()
    if not user_data:  # 如果找不到环境变量，退出循环
        break

    parts = user_data.split()
    if len(parts) == 3:
        forum_url, username, password = parts
        if not forum_url.startswith(('http://', 'https://')):
            forum_url = f'https://{forum_url}'
        domain = urlparse(forum_url).netloc
        view_count = int(os.getenv(f"VIEW_COUNT_{index}", "1000"))
        scroll_duration = int(os.getenv(f"SCROLL_DURATION_{index}", "5"))
        accounts.append({
            'forum_url': forum_url,
            'username': username,
            'password': password,
            'domain': domain,
            'view_count': view_count,
            'scroll_duration': scroll_duration
        })
    index += 1

if not accounts:
    logging.error("❌ 未找到有效的账户配置")
    exit(1)

logging.info(f"✅ 成功解析 {len(accounts)} 个账户配置")
for acc in accounts:
    logging.info(f"   📍 {acc['domain']} - {acc['username']}")

browse_count = 0
connect_info = ""
like_count = 0
account_info = []

user_count = len(accounts)

logging.info(f"共找到 {user_count} 个账户")


def load_send():
    cur_path = path.abspath(path.dirname(__file__))
    if path.exists(cur_path + "/notify.py"):
        try:
            from notify import send
            return send
        except ImportError:
            return False
    else:
        return False


class TopicLoader:
    def __init__(self, driver, domain):
        self.driver = driver
        self.domain = domain
        self.daily_requirements = self._load_daily_requirements()
        self.progress = {
            'browse_count': 0,
            'total_time': 0
        }
        logging.info(f"🎯 {self.domain} 的每日目标：")
        logging.info(f"   - 需要浏览帖子数：{self.daily_requirements['daily_views']}")
        logging.info(f"   - 需要阅读时间：{self.daily_requirements['daily_time']}秒")

    def _load_daily_requirements(self):
        try:
            with open('daily_requirements.json', 'r', encoding='utf-8') as f:
                requirements = json.load(f)
                if self.domain in requirements:
                    logging.info(f"✅ 已从配置文件加载 {self.domain} 的要求")
                    return requirements[self.domain]
                else:
                    logging.info(f"⚠️ 未找到 {self.domain} 的配置，使用默认值：100浏览量/200秒")
                    return {
                        'daily_views': 50,
                        'daily_time': 180
                    }
        except FileNotFoundError:
            logging.warning(f"⚠️ 未找到 daily_requirements.json，使用默认值：100浏览量/200秒")
            return {
                'daily_views': 50,
                'daily_time': 180
            }
        except json.JSONDecodeError:
            logging.error(f"❌ daily_requirements.json 格式错误，使用默认值：100浏览量/200秒")
            return {
                'daily_views': 50,
                'daily_time': 180
            }

    def has_met_requirements(self):
        req = self.daily_requirements
        views_met = self.progress['browse_count'] >= req['daily_views']
        time_met = self.progress['total_time'] >= req['daily_time']

        if views_met and time_met:
            logging.info("✅ 已达到所有要求！")
            logging.info(f"   - 浏览量：{self.progress['browse_count']}/{req['daily_views']}")
            logging.info(f"   - 阅读时间：{self.progress['total_time']:.1f}/{req['daily_time']}秒")

        return views_met and time_met

    def remaining_requirements(self):
        req = self.daily_requirements
        remaining = {
            'views': max(0, req['daily_views'] - self.progress['browse_count']),
            'time': max(0, req['daily_time'] - self.progress['total_time'])
        }

        logging.info("📊 当前进度：")
        logging.info(f"   - 已浏览：{self.progress['browse_count']}/{req['daily_views']} 个帖子")
        logging.info(f"   - 已阅读：{self.progress['total_time']:.1f}/{req['daily_time']} 秒")
        if remaining['views'] > 0 or remaining['time'] > 0:
            logging.info("⏳ 还需要：")
            if remaining['views'] > 0:
                logging.info(f"   - 浏览 {remaining['views']} 个帖子")
            if remaining['time'] > 0:
                logging.info(f"   - 阅读 {remaining['time']:.1f} 秒")

        return remaining

    def load_topics(self, scroll_duration=5):
        """Load topics by scrolling the page"""
        logging.info(f"📜 开始滚动加载帖子，持续 {scroll_duration} 秒...")
        end_time = time.time() + scroll_duration
        actions = ActionChains(self.driver)

        while time.time() < end_time:
            actions.scroll_by_amount(0, 500).perform()
            time.sleep(0.1)

        topics = self.driver.find_elements(By.CSS_SELECTOR, "#list-area .title")
        logging.info(f"✨ 本次加载到 {len(topics)} 个帖子")
        return topics

    def update_progress(self, browse_time):
        """Update progress after viewing a topic"""
        self.progress['browse_count'] += 1
        self.progress['total_time'] += browse_time
        logging.info("📈 更新进度：")
        logging.info(f"   - 总浏览量：{self.progress['browse_count']}")
        logging.info(f"   - 总阅读时间：{self.progress['total_time']:.1f}秒")

    def reset_to_main_page(self):
        """Return to the main forum page to load more topics"""
        logging.info("🔄 返回主页重新加载帖子...")
        current_url = self.driver.current_url
        base_url = current_url.split('?')[0].split('#')[0]
        self.driver.get(base_url)
        time.sleep(2)  # Wait for page to load
        logging.info("✅ 页面重新加载完成")


class LinuxDoBrowser:
    def __init__(self) -> None:
        logging.info("启动 Selenium")

        global chrome_options
        chrome_options = webdriver.ChromeOptions()

        # 青龙面板特定的 Chrome 选项
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument('--headless=new')  # 使用新的 headless 模式
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--start-maximized")
        chrome_options.add_argument("--disable-notifications")
        chrome_options.add_argument("--ignore-certificate-errors")
        chrome_options.add_argument('--allow-running-insecure-content')
        chrome_options.add_argument("--disable-popup-blocking")

        # 添加 user-agent
        chrome_options.add_argument(
            '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

        # 禁用自动化标志
        chrome_options.add_experimental_option('excludeSwitches', ['enable-automation'])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        # 设置页面加载策略
        chrome_options.page_load_strategy = 'normal'

        # 检查 chromedriver 路径
        global chromedriver_path
        chromedriver_path = shutil.which("chromedriver")

        if not chromedriver_path:
            logging.error("chromedriver 未找到，请确保已安装并配置正确的路径。")
            exit(1)

        self.driver = None

    def create_driver(self):
        try:
            service = Service(chromedriver_path)
            self.driver = webdriver.Chrome(service=service, options=chrome_options)

            # 删除 navigator.webdriver 标志
            self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                'source': '''
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    })
                '''
            })

            # 设置页面加载超时
            self.driver.set_page_load_timeout(30)
            self.driver.implicitly_wait(10)

            return True

        except Exception as e:
            logging.error(f"创建 WebDriver 失败: {e}")
            return False

    def simulate_typing(self, element, text, typing_speed=0.1, random_delay=True):
        for char in text:
            element.send_keys(char)
            if random_delay:
                time.sleep(typing_speed + random.uniform(0, 0.1))
            else:
                time.sleep(typing_speed)

    def login(self) -> bool:
        try:
            logging.info(f"--- 开始尝试登录：{self.username}---")

            # 先等待页面加载完成
            WebDriverWait(self.driver, 20).until(
                lambda driver: driver.execute_script('return document.readyState') == 'complete'
            )

            # 确保在点击之前页面已完全加载
            time.sleep(3)

            try:
                login_button = WebDriverWait(self.driver, 20).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, ".login-button .d-button-label"))
                )
                self.driver.execute_script("arguments[0].click();", login_button)
            except:
                logging.info("尝试备用登录按钮选择器")
                login_button = WebDriverWait(self.driver, 20).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "button.login-button"))
                )
                self.driver.execute_script("arguments[0].click();", login_button)

            # 等待登录表单出现
            WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.ID, "login-form"))
            )

            # 输入用户名
            username_field = WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.ID, "login-account-name"))
            )
            username_field.clear()
            time.sleep(1)
            self.simulate_typing(username_field, self.username)

            # 输入密码
            password_field = WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.ID, "login-account-password"))
            )
            password_field.clear()
            time.sleep(1)
            self.simulate_typing(password_field, self.password)

            # 提交登录
            submit_button = WebDriverWait(self.driver, 20).until(
                EC.element_to_be_clickable((By.ID, "login-button"))
            )
            time.sleep(1)
            self.driver.execute_script("arguments[0].click();", submit_button)

            # 验证登录结果
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "#current-user"))
                )
                logging.info("登录成功")
                return True
            except TimeoutException:
                error_element = self.driver.find_elements(By.CSS_SELECTOR, "#modal-alert.alert-error")
                if error_element:
                    logging.error(f"登录失败：{error_element[0].text}")
                else:
                    logging.error("登录失败：无法验证登录状态")
                return False

        except Exception as e:
            logging.error(f"登录过程发生错误：{str(e)}")
            # 保存截图以便调试
            try:
                self.driver.save_screenshot("login_error.png")
                logging.info("已保存错误截图到 login_error.png")
            except:
                pass
            return False

    def click_topic(self):
        try:
            topic_loader = TopicLoader(self.driver, urlparse(self.driver.current_url).netloc)

            while not topic_loader.has_met_requirements():
                logging.info("--- 开始滚动页面加载更多帖子 ---")
                topics = topic_loader.load_topics(self.scroll_duration)
                total_topics = len(topics)
                remaining = topic_loader.remaining_requirements()

                logging.info(f"共找到 {total_topics} 个帖子")
                logging.info(f"还需要浏览 {remaining['views']} 个帖子，累计阅读时间还差 {remaining['time']} 秒")

                if total_topics == 0:
                    logging.warning("没有找到任何帖子，将重新加载页面")
                    topic_loader.reset_to_main_page()
                    continue

                for idx, topic in enumerate(topics):
                    if topic_loader.has_met_requirements():
                        logging.info("已达到每日要求，停止浏览")
                        break

                    try:
                        parent_element = topic.find_element(By.XPATH, "./ancestor::tr")

                        is_pinned = parent_element.find_elements(
                            By.CSS_SELECTOR, ".topic-statuses .pinned"
                        )

                        if is_pinned:
                            logging.info(f"跳过置顶的帖子：{topic.text.strip()}")
                            continue

                        views_element = parent_element.find_element(
                            By.CSS_SELECTOR, ".num.views .number"
                        )
                        views_title = views_element.get_attribute("title")

                        if "此话题已被浏览 " in views_title and " 次" in views_title:
                            views_count_str = views_title.split("此话题已被浏览 ")[1].split(" 次")[0]
                            views_count = int(views_count_str.replace(",", ""))
                        else:
                            logging.warning(f"无法解析浏览次数，跳过该帖子: {views_title}")
                            continue

                        article_title = topic.text.strip()
                        logging.info(f"打开第 {idx + 1}/{total_topics} 个帖子 ：{article_title}")
                        article_url = topic.get_attribute("href")

                        try:
                            self.driver.execute_script("window.open('');")
                            self.driver.switch_to.window(self.driver.window_handles[-1])

                            browse_start_time = time.time()
                            self.driver.set_page_load_timeout(10)
                            try:
                                self.driver.get(article_url)
                            except TimeoutException:
                                logging.warning(f"加载帖子超时: {article_title}")
                                raise

                            global browse_count
                            browse_count += 1

                            if views_count > self.view_count:
                                logging.info(f"📈 当前帖子浏览量为{views_count} 大于设定值 {self.view_count}，🥳 开始进行点赞操作")
                                self.click_like()

                            scroll_duration = random.uniform(5, 10)
                            try:
                                while time.time() - browse_start_time < scroll_duration:
                                    self.driver.execute_script(
                                        "window.scrollBy(0, window.innerHeight);"
                                    )
                                    time.sleep(1)
                            except Exception as e:
                                logging.warning(f"在滚动过程中发生错误: {e}")

                            browse_end_time = time.time()
                            total_browse_time = browse_end_time - browse_start_time
                            topic_loader.update_progress(total_browse_time)
                            logging.info(f"浏览该帖子时间: {total_browse_time:.2f}秒")

                        except Exception as e:
                            logging.error(f"处理帖子时发生错误: {e}")

                        finally:
                            if len(self.driver.window_handles) > 1:
                                self.driver.close()
                                self.driver.switch_to.window(self.driver.window_handles[0])
                            logging.info(f"已关闭第 {idx + 1}/{total_topics} 个帖子 ： {article_title}")

                    except Exception as e:
                        logging.error(f"处理帖子 {idx + 1} 时发生错误: {e}")
                        continue

                if not topic_loader.has_met_requirements():
                    logging.info("当前页面帖子已处理完，但未达到要求，将重新加载页面")
                    topic_loader.reset_to_main_page()

            logging.info("所有要求已完成")

        except Exception as e:
            logging.error(f"click_topic 方法发生错误: {e}")

    def click_like(self):
        try:
            global like_count
            like_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, ".btn-toggle-reaction-like")
                )
            )

            if "移除此赞" in like_button.get_attribute("title"):
                logging.info("该帖子已点赞，跳过点赞操作。")
            else:
                self.driver.execute_script("arguments[0].click();", like_button)
                like_count += 1
                logging.info("点赞帖子成功")

        except TimeoutException:
            logging.error("点赞操作失败：点赞按钮定位超时")
        except WebDriverException as e:
            logging.error(f"点赞操作失败: {e}")
        except Exception as e:
            logging.error(f"未知错误导致点赞操作失败: {e}")
    def run(self):
        """主运行流程"""
        global browse_count
        global like_count

        for i in range(user_count):
            start_time = time.time()
            self.username = accounts[i]['username']
            self.password = accounts[i]['password']
            self.view_count = accounts[i]['view_count']
            self.scroll_duration = accounts[i]['scroll_duration']
            domain = accounts[i]['domain']

            logging.info(f"▶️▶️▶️  开始执行第{i + 1}个账号: {domain} - {self.username}")

            try:
                if not self.create_driver():
                    logging.error("创建浏览器实例失败，跳过当前账号")
                    continue

                logging.info(f"导航到 {domain}")
                self.driver.get(accounts[i]['forum_url'])

                if not self.login():
                    logging.error(f"{self.username} 登录失败")
                    continue

                self.click_topic()
                logging.info(f"🎉 恭喜：{self.username}，帖子浏览全部完成")

                self.logout()

            except WebDriverException as e:
                logging.error(f"WebDriver 初始化失败: {e}")
                logging.info("请尝试重新搭建青龙面板或换个机器运行")
                exit(1)
            except Exception as e:
                logging.error(f"运行过程中出错: {e}")
            finally:
                if self.driver is not None:
                    self.driver.quit()

            end_time = time.time()
            spend_time = int((end_time - start_time) // 60)

            account_info.append({
                "domain": domain,
                "username": self.username,
                "browse_count": browse_count,
                "like_count": like_count,
                "spend_time": spend_time
            })

            # 重置状态
            browse_count = 0
            like_count = 0

        logging.info("\n" + "="*50)
        logging.info("📊 执行报告")
        logging.info("="*50)

        total_browse = sum(r['browse_count'] for r in account_info)
        total_like = sum(r['like_count'] for r in account_info)

        # 生成摘要
        summary = f"运行完成\n\n"
        summary += f"总浏览: {total_browse} 个帖子\n"
        summary += f"总点赞: {total_like} 次\n\n"

        for info in account_info:
            summary += f"{info['domain']} - {info['username']}\n"
            summary += f"浏览: {info['browse_count']} | 点赞: {info['like_count']} | 用时: {info['spend_time']}分钟\n\n"
            # 控制台输出
            logging.info(f"✅ {info['domain']} - {info['username']}")
            logging.info(f"   浏览:{info['browse_count']} 点赞:{info['like_count']} 用时:{info['spend_time']}分钟")

        logging.info("-" * 50)
        logging.info(f"📚 总浏览: {total_browse} 个帖子")
        logging.info(f"👍 总点赞: {total_like} 次")

        send = load_send()
        if callable(send):
            send("Discourse浏览帖子", summary)
        else:
            logging.info("📤 未配置通知推送")


if __name__ == "__main__":
    try:
        linuxdo_browser = LinuxDoBrowser()
        linuxdo_browser.run()
    except KeyboardInterrupt:
        logging.info("\n⏹️ 用户中断执行")
    except Exception as e:
        logging.error(f"❌ 程序异常: {e}")
    finally:
        logging.info("🏁 程序结束")