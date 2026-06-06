import base64
import time
import requests
import tempfile
import os
import numpy as np
import cv2
import imageio
import threading
import queue
from playwright.sync_api import sync_playwright


class PlaywrightThread(threading.Thread):
    """独立线程中运行 Playwright，避免与 asyncio 事件循环冲突。"""

    def __init__(self):
        super().__init__(daemon=True)
        self.command_queue = queue.Queue()
        self.result_queue = queue.Queue()
        self.running = True
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.width = 375
        self.height = 812
        self.lock = threading.Lock()
        self.is_stuck = False

    # ------------------------------------------------------------------
    # Thread loop
    # ------------------------------------------------------------------
    def run(self):
        while self.running:
            try:
                self.playwright = sync_playwright().start()
                while self.running:
                    try:
                        cmd = self.command_queue.get(timeout=0.1)
                        if cmd is None:
                            break
                        self._execute_command(cmd)
                    except queue.Empty:
                        continue
                    except Exception as e:
                        self.result_queue.put(('error', str(e)))
            except Exception as e:
                print(f"Playwright thread error: {e}")
                time.sleep(1)
            finally:
                try:
                    if self.browser:
                        self.browser.close()
                except Exception:
                    pass
                try:
                    if self.playwright:
                        self.playwright.stop()
                except Exception:
                    pass
                self.playwright = None
                self.browser = None
                self.context = None
                self.page = None

    # ------------------------------------------------------------------
    # Helpers used inside commands
    # ------------------------------------------------------------------
    def _draw_mark_on_screenshot(self, screenshot_bytes, x, y):
        img_array = np.frombuffer(screenshot_bytes, np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        cv2.circle(img, (int(x), int(y)), 15, (0, 0, 255), 3)
        cv2.circle(img, (int(x), int(y)), 5, (0, 0, 255), -1)
        _, marked_screenshot = cv2.imencode('.png', img)
        return marked_screenshot.tobytes()

    def _take_screenshot(self):
        try:
            return self.page.screenshot(type='png', timeout=5000)
        except Exception:
            return self.page.screenshot(type='png', timeout=10000)

    def _execute_command(self, cmd):
        try:
            cmd_type = cmd['type']

            if cmd_type == 'init_browser':
                self.browser = self.playwright.chromium.launch(
                    headless=cmd['headless']
                )
                self.context = self.browser.new_context(
                    viewport={'width': self.width, 'height': self.height}
                )
                self.page = self.context.new_page()
                self.page.set_default_timeout(5000)
                self.result_queue.put(('success', None))

            elif cmd_type == 'goto':
                self.page.goto(
                    cmd['url'], wait_until="domcontentloaded", timeout=10000
                )
                self.result_queue.put(('success', None))

            elif cmd_type == 'screenshot':
                self.result_queue.put(('success', self._take_screenshot()))

            elif cmd_type == 'click':
                self.page.mouse.click(cmd['x'], cmd['y'])
                time.sleep(0.3)
                self.result_queue.put(('success', self._take_screenshot()))

            elif cmd_type == 'swipe':
                self.page.mouse.move(cmd['x1'], cmd['y1'])
                self.page.mouse.down()
                self.page.mouse.move(cmd['x2'], cmd['y2'], steps=cmd['steps'])
                self.page.mouse.up()
                time.sleep(0.3)
                self.result_queue.put(('success', self._take_screenshot()))

            elif cmd_type == 'mark_point':
                screenshot_bytes = self._take_screenshot()
                marked = self._draw_mark_on_screenshot(
                    screenshot_bytes, cmd['x'], cmd['y']
                )
                self.result_queue.put(('success', marked))

            elif cmd_type == 'type':
                self.page.keyboard.type(cmd['text'])
                self.page.keyboard.press("Enter")
                time.sleep(0.3)
                self.result_queue.put(('success', self._take_screenshot()))

            elif cmd_type == 'wait':
                time.sleep(cmd['seconds'])
                self.result_queue.put(('success', self._take_screenshot()))

            elif cmd_type == 'click_selector':
                self.page.click(cmd['selector'], timeout=5000)
                time.sleep(0.3)
                self.result_queue.put(('success', self._take_screenshot()))

            elif cmd_type == 'fill':
                self.page.fill(
                    cmd['selector'], cmd['value'], timeout=5000
                )
                time.sleep(0.3)
                self.result_queue.put(('success', self._take_screenshot()))

            elif cmd_type == 'press_key':
                self.page.click('body', timeout=5000)
                self.page.keyboard.press(cmd['key'])
                time.sleep(0.3)
                self.result_queue.put(('success', self._take_screenshot()))

            elif cmd_type == 'query_selector_all':
                elements = self.page.query_selector_all(cmd['selector'])
                elements_info = []
                for el in elements:
                    try:
                        is_visible = el.is_visible()
                        box = el.bounding_box() if is_visible else None
                        test_id = el.get_attribute("data-testid")
                        elements_info.append({
                            'is_visible': is_visible,
                            'box': box,
                            'test_id': test_id,
                        })
                    except Exception:
                        pass
                self.result_queue.put(('success', elements_info))

            elif cmd_type == 'evaluate':
                self.result_queue.put(
                    ('success', self.page.evaluate(cmd['script']))
                )

            elif cmd_type == 'locator_bounding_box':
                box = self.page.locator(cmd['selector']).bounding_box()
                self.result_queue.put(('success', box))

            elif cmd_type == 'close':
                self.result_queue.put(('success', None))

        except Exception as e:
            self.result_queue.put(('error', str(e)))

    # ------------------------------------------------------------------
    # Public API (called from the main thread)
    # ------------------------------------------------------------------
    def send_command(self, cmd, timeout=15):
        with self.lock:
            self.command_queue.put(cmd)
            try:
                result_type, result = self.result_queue.get(timeout=timeout)
            except queue.Empty:
                self.is_stuck = True
                raise Exception(
                    f"Playwright command timed out after {timeout} seconds"
                )
            if result_type == 'error':
                raise Exception(result)
            return result

    def stop(self):
        self.running = False
        self.command_queue.put(None)
        self.join(timeout=5)


class VideoChecker:
    def __init__(self, target_url="http://127.0.0.1:5000", page_proxy=None):
        self.base_url = target_url
        self.page_proxy = page_proxy

    def get_backend_state(self):
        return requests.get(f"{self.base_url}/api/debug/state").json()

    def check_is_liked(self, video_index):
        state = self.get_backend_state()
        if video_index < len(state):
            return state[video_index].get('is_liked', False)
        return False

    def check_is_collected(self, video_index):
        state = self.get_backend_state()
        if video_index < len(state):
            return state[video_index].get('is_collected', False)
        return False

    def check_has_comment(self, video_index, content=None):
        state = self.get_backend_state()
        if video_index >= len(state):
            return False
        comments = state[video_index].get('comments', [])
        if content is None:
            return len(comments) > 0
        return any(
            content.strip(' \n') in c['text'].strip(' \n')
            for c in comments
        )

    def check_is_reported(self, video_index,
                          expected_cat=None, expected_reason=None):
        state = self.get_backend_state()
        if video_index >= len(state):
            return False
        reports = state[video_index].get('reports', [])
        if not reports:
            return False
        for r in reports:
            if expected_cat is not None and r.get('category') != expected_cat:
                continue
            if expected_reason is not None:
                actual = (r.get('reason', '') or '').strip(' \n')
                if actual != expected_reason.strip(' \n'):
                    continue
            return True
        return False

    def check_current_viewing(self, env, index):
        selector = f'.video-item:nth-child({index + 1})'
        box = self.page_proxy.send_command({
            'type': 'locator_bounding_box',
            'selector': selector,
        })
        if not box:
            return False
        return abs(box['y']) < 50

    def check_playback(self, env, index,
                       target_pct=None, target_sec=None, tolerance=0.05):
        script = f"""() => {{
            const v = document.querySelectorAll('.main-video')[{index}];
            return {{ cur: v.currentTime, dur: v.duration }};
        }}"""
        data = self.page_proxy.send_command({'type': 'evaluate', 'script': script})
        cur, dur = data['cur'], data['dur']
        if dur == 0:
            return False
        if target_pct is not None:
            return abs((cur / dur) - target_pct) <= tolerance
        elif target_sec is not None:
            return abs(cur - target_sec) <= (dur * tolerance)
        else:
            raise ValueError("Either target_pct or target_sec must be provided")


class VideoAgentEnv:

    def __init__(self, data, target_url="http://127.0.0.1", port=5000,
                 headless=True):
        self.width = 375
        self.height = 812
        self.target_url = f"{target_url}:{port}"
        self.headless = headless
        self.data = data

        self.playwright_thread = PlaywrightThread()
        self.playwright_thread.start()
        time.sleep(0.5)

        try:
            resp = requests.post(
                f"{self.target_url}/api/reset", json=self.data
            )
            if resp.status_code != 200:
                print(f"Error: Backend sync failed, status code: {resp.status_code}")
                print(resp.json())
        except Exception as e:
            raise e

        self.playwright_thread.send_command({
            'type': 'init_browser', 'headless': self.headless,
        })
        self.playwright_thread.send_command({
            'type': 'goto', 'url': self.target_url,
        })

        self.checker = VideoChecker(self.target_url, self.playwright_thread)

    # ------------------------------------------------------------------
    # System
    # ------------------------------------------------------------------
    def get_screenshot(self):
        screenshot_bytes = self.playwright_thread.send_command({
            'type': 'screenshot'
        })
        return base64.b64encode(screenshot_bytes).decode('utf-8')

    def _frames_to_video(self, frames, fps=2):
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp:
            video_path = tmp.name
        try:
            first_frame = cv2.imdecode(
                np.frombuffer(base64.b64decode(frames[0]), np.uint8),
                cv2.IMREAD_COLOR,
            )
            height, width = first_frame.shape[:2]
            new_width = ((width + 15) // 16) * 16
            new_height = ((height + 15) // 16) * 16
            writer = imageio.get_writer(video_path, fps=fps, codec='libx264')
            for frame_b64 in frames:
                frame = cv2.imdecode(
                    np.frombuffer(base64.b64decode(frame_b64), np.uint8),
                    cv2.IMREAD_COLOR,
                )
                if frame.shape[0] != new_height or frame.shape[1] != new_width:
                    frame = cv2.resize(frame, (new_width, new_height))
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                writer.append_data(frame_rgb)
            writer.close()
            with open(video_path, 'rb') as f:
                video_bytes = f.read()
            return base64.b64encode(video_bytes).decode('utf-8')
        finally:
            try:
                os.unlink(video_path)
            except Exception:
                pass

    def get_recording(self, seconds, fps=2, use_video=True):
        frames = []
        num_frames = max(1, int(seconds * fps))
        interval = seconds / num_frames
        for i in range(num_frames):
            if i > 0:
                time.sleep(interval)
            frames.append(self.get_screenshot())

        if use_video:
            video = self._frames_to_video(frames, fps=fps)
        else:
            video = None
        return {'video': video, 'frames': frames}

    def get_semantic_snapshot(self):
        elements_info = self.playwright_thread.send_command({
            'type': 'query_selector_all',
            'selector': '[data-testid]',
        })
        snapshot = []
        for el_info in elements_info:
            if el_info['is_visible'] and el_info['box']:
                box = el_info['box']
                snapshot.append({
                    "test_id": el_info['test_id'],
                    "center_x": box['x'] + box['width'] / 2,
                    "center_y": box['y'] + box['height'] / 2,
                    "rect": box,
                })
        return snapshot

    def close(self):
        try:
            self.playwright_thread.send_command({'type': 'close'})
        except Exception:
            pass
        self.playwright_thread.stop()

    # ------------------------------------------------------------------
    # Low-level agent actions
    # ------------------------------------------------------------------
    def click_at(self, x, y):
        screenshot_bytes = self.playwright_thread.send_command({
            'type': 'click', 'x': x, 'y': y,
        })
        return base64.b64encode(screenshot_bytes).decode('utf-8')

    def swipe(self, start_x, start_y, end_x, end_y, steps=10):
        screenshot_bytes = self.playwright_thread.send_command({
            'type': 'swipe',
            'x1': start_x, 'y1': start_y,
            'x2': end_x, 'y2': end_y,
            'steps': steps,
        })
        return base64.b64encode(screenshot_bytes).decode('utf-8')

    def type_text(self, text):
        screenshot_bytes = self.playwright_thread.send_command({
            'type': 'type', 'text': text,
        })
        return base64.b64encode(screenshot_bytes).decode('utf-8')

    def wait(self, seconds):
        screenshot_bytes = self.playwright_thread.send_command({
            'type': 'wait', 'seconds': seconds,
        })
        return base64.b64encode(screenshot_bytes).decode('utf-8')

    def mark_point(self, x, y):
        screenshot_bytes = self.playwright_thread.send_command({
            'type': 'mark_point', 'x': x, 'y': y,
        })
        return base64.b64encode(screenshot_bytes).decode('utf-8')

    def watch(self, seconds, fps=2, use_video=True):
        result = self.get_recording(seconds, fps=fps, use_video=use_video)
        return result["video"] if use_video else result["frames"]

    # ------------------------------------------------------------------
    # High-level agent actions (UI-driven)
    # ------------------------------------------------------------------
    def previous_video(self):
        screenshot_bytes = self.playwright_thread.send_command({
            'type': 'press_key', 'key': 'ArrowUp',
        })
        return base64.b64encode(screenshot_bytes).decode('utf-8')

    def next_video(self):
        screenshot_bytes = self.playwright_thread.send_command({
            'type': 'press_key', 'key': 'ArrowDown',
        })
        return base64.b64encode(screenshot_bytes).decode('utf-8')

    def toggle_like(self):
        try:
            screenshot_bytes = self.playwright_thread.send_command({
                'type': 'click_selector',
                'selector': '[data-testid="like-btn"]',
            })
            return base64.b64encode(screenshot_bytes).decode('utf-8')
        except Exception:
            return None

    def open_comments(self):
        try:
            screenshot_bytes = self.playwright_thread.send_command({
                'type': 'click_selector',
                'selector': '[data-testid="comment-btn"]',
            })
            return base64.b64encode(screenshot_bytes).decode('utf-8')
        except Exception:
            return None

    def submit_comment(self, text):
        self.open_comments()
        time.sleep(0.3)
        self.playwright_thread.send_command({
            'type': 'fill',
            'selector': '[data-testid="comment-input-field"]',
            'value': text,
        })
        screenshot_bytes = self.playwright_thread.send_command({
            'type': 'click_selector',
            'selector': '[data-testid="comment-submit"]',
        })
        return base64.b64encode(screenshot_bytes).decode('utf-8')

    def close_comment(self):
        try:
            screenshot_bytes = self.playwright_thread.send_command({
                'type': 'click_selector',
                'selector': '[data-testid="comment-close-btn"]',
            })
            return base64.b64encode(screenshot_bytes).decode('utf-8')
        except Exception:
            return None

    def toggle_collect(self):
        try:
            screenshot_bytes = self.playwright_thread.send_command({
                'type': 'click_selector',
                'selector': '[data-testid="collect-btn"]',
            })
            return base64.b64encode(screenshot_bytes).decode('utf-8')
        except Exception:
            return None

    def action_report(self, reason_index=0, text=""):
        self.playwright_thread.send_command({
            'type': 'click_selector',
            'selector': '[data-testid="report-btn"]',
        })
        time.sleep(0.3)
        self.playwright_thread.send_command({
            'type': 'fill',
            'selector': '[data-testid="report-text-area"]',
            'value': text,
        })
        screenshot_bytes = self.playwright_thread.send_command({
            'type': 'click_selector',
            'selector': '[data-testid="report-confirm"]',
        })
        return base64.b64encode(screenshot_bytes).decode('utf-8')


if __name__ == "__main__":
    import json
    with open("data/feed/fake_news_detection.json", "r") as f:
        data = json.load(f)
    env = VideoAgentEnv(data)
    env.close()
