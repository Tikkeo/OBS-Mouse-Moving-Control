import obspython as obs
import pyautogui
import cv2
import numpy as np
import time
import threading
import os
from collections import deque

script_settings = None

is_running = False
capture_thread = None
target_image = None
tracking_active = False

frame_queue = deque(maxlen=5)
processing_lock = threading.Lock()

mouse_trail = deque(maxlen=10)
last_mouse_pos = None

brutal_mode_active = False
brutal_mode_warning_shown = False

class MouseController:
    def __init__(self):
        self.smoothing_factor = 0.3
        self.move_speed = 1.0
        self.enable_smoothing = True
        self.enable_speed_control = False

    def move_to_smooth(self, target_x, target_y):
        global last_mouse_pos, mouse_trail

        current_pos = pyautogui.position()

        if self.enable_smoothing and last_mouse_pos:
            smooth_x = int(last_mouse_pos[0] + (target_x - last_mouse_pos[0]) * self.smoothing_factor)
            smooth_y = int(last_mouse_pos[1] + (target_y - last_mouse_pos[1]) * self.smoothing_factor)

            if self.enable_speed_control:
                smooth_x = int(current_pos[0] + (smooth_x - current_pos[0]) * self.move_speed)
                smooth_y = int(current_pos[1] + (smooth_y - current_pos[1]) * self.move_speed)

            pyautogui.moveTo(smooth_x, smooth_y, duration=0.05)
            last_mouse_pos = (smooth_x, smooth_y)
        else:
            pyautogui.moveTo(target_x, target_y, duration=0.05)
            last_mouse_pos = (target_x, target_y)

        mouse_trail.append((target_x, target_y))

    def click(self, button='left', clicks=1, interval=0.1):
        for _ in range(clicks):
            pyautogui.click(button=button)
            time.sleep(interval)

    def right_click(self):
        pyautogui.click(button='right')

    def scroll(self, clicks=1):
        pyautogui.scroll(clicks)

    def press_key(self, key):
        pyautogui.press(key)

    def hold_key(self, key, duration=1.0):
        pyautogui.keyDown(key)
        time.sleep(duration)
        pyautogui.keyUp(key)

mouse_controller = MouseController()

class SnapController:
    def __init__(self):
        self.enable_snap = False
        self.enable_grid_snap = False
        self.enable_edge_snap = False
        self.enable_center_snap = False
        self.enable_element_snap = False
        self.grid_size = 50
        self.snap_threshold = 10
        self.element_sensitivity = 0.5

        self.sources = []
        self.detected_elements = []

    def set_sources(self, sources):
        self.sources = sources

    def detect_elements(self, screenshot, template=None):
        self.detected_elements = []

        if not self.enable_element_snap:
            return

        try:
            gray = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)

            edges = cv2.Canny(gray, 50, 150)
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            for contour in contours:
                area = cv2.contourArea(contour)
                if area > 500 and area < 50000:
                    x, y, w, h = cv2.boundingRect(contour)
                    self.detected_elements.append({
                        'type': 'edge',
                        'x': x,
                        'y': y,
                        'w': w,
                        'h': h,
                        'center_x': x + w // 2,
                        'center_y': y + h // 2,
                        'area': area
                    })

            if template is not None:
                result = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)
                min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

                if max_val >= self.element_sensitivity:
                    h, w = template.shape[:2]
                    self.detected_elements.append({
                        'type': 'template',
                        'x': max_loc[0],
                        'y': max_loc[1],
                        'w': w,
                        'h': h,
                        'center_x': max_loc[0] + w // 2,
                        'center_y': max_loc[1] + h // 2,
                        'confidence': max_val
                    })

            color_regions = self._detect_color_regions(screenshot)
            self.detected_elements.extend(color_regions)

        except Exception as e:
            obs.script_log(obs.LOG_ERROR, f"元素检测错误: {str(e)}")

    def _detect_color_regions(self, screenshot):
        regions = []
        try:
            hsv = cv2.cvtColor(screenshot, cv2.COLOR_BGR2HSV)

            lower_colors = [
                np.array([0, 50, 50]),
                np.array([25, 50, 50]),
                np.array([50, 50, 50]),
                np.array([100, 50, 50]),
            ]

            for i, lower in enumerate(lower_colors):
                upper = np.array([lower[0] + 30, 255, 255])
                mask = cv2.inRange(hsv, lower, upper)

                contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

                for contour in contours:
                    area = cv2.contourArea(contour)
                    if area > 1000:
                        x, y, w, h = cv2.boundingRect(contour)
                        regions.append({
                            'type': f'color_{i}',
                            'x': x,
                            'y': y,
                            'w': w,
                            'h': h,
                            'center_x': x + w // 2,
                            'center_y': y + h // 2,
                            'area': area
                        })
        except:
            pass
        return regions

    def snap_to_element(self, x, y, target_pos=None):
        if not self.enable_element_snap or not self.detected_elements:
            return x, y

        if target_pos:
            target_x, target_y = target_pos
        else:
            target_x, target_y = x, y

        closest_element = None
        min_distance = float('inf')

        for element in self.detected_elements:
            elem_cx = element['center_x']
            elem_cy = element['center_y']

            distance = abs(x - elem_cx) + abs(y - elem_cy)

            if distance < min_distance and distance < 200:
                min_distance = distance
                closest_element = element

        if closest_element:
            snap_x = closest_element['center_x']
            snap_y = closest_element['center_y']

            if abs(x - snap_x) < self.snap_threshold * 3:
                x = snap_x
            if abs(y - snap_y) < self.snap_threshold * 3:
                y = snap_y

        return x, y

    def snap_to_grid(self, x, y):
        if not self.enable_grid_snap:
            return x, y

        grid_x = round(x / self.grid_size) * self.grid_size
        grid_y = round(y / self.grid_size) * self.grid_size

        if abs(x - grid_x) <= self.snap_threshold:
            x = grid_x
        if abs(y - grid_y) <= self.snap_threshold:
            y = grid_y

        return x, y

    def snap_to_edge(self, x, y, width, height, source_bounds):
        if not self.enable_edge_snap or not source_bounds:
            return x, y

        for sb_x, sb_y, sb_w, sb_h in source_bounds:
            if abs((x + width) - sb_x) <= self.snap_threshold:
                x = sb_x - width
            if abs(x - (sb_x + sb_w)) <= self.snap_threshold:
                x = sb_x + sb_w
            if abs((y + height) - sb_y) <= self.snap_threshold:
                y = sb_y - height
            if abs(y - (sb_y + sb_h)) <= self.snap_threshold:
                y = sb_y + sb_h

        return x, y

    def snap_to_center(self, x, y, width, height, canvas_width, canvas_height):
        if not self.enable_center_snap:
            return x, y

        center_x = canvas_width // 2
        center_y = canvas_height // 2

        item_center_x = x + width // 2
        item_center_y = y + height // 2

        if abs(item_center_x - center_x) <= self.snap_threshold:
            x = center_x - width // 2
        if abs(item_center_y - center_y) <= self.snap_threshold:
            y = center_y - height // 2

        return x, y

    def apply_snap(self, x, y, width=0, height=0, canvas_width=1920, canvas_height=1080, source_bounds=None, target_pos=None):
        if not self.enable_snap:
            return x, y

        x, y = self.snap_to_grid(x, y)

        if source_bounds:
            x, y = self.snap_to_edge(x, y, width, height, source_bounds)

        if self.enable_center_snap:
            x, y = self.snap_to_center(x, y, width, height, canvas_width, canvas_height)

        if self.enable_element_snap:
            x, y = self.snap_to_element(x, y, target_pos)

        return x, y

snap_controller = SnapController()

MATCH_ALGORITHMS = {
    'TM_CCOEFF_NORMED': cv2.TM_CCOEFF_NORMED,
    'TM_CCORR_NORMED': cv2.TM_CCORR_NORMED,
    'TM_SQDIFF': cv2.TM_SQDIFF,
    'TM_SQDIFF_NORMED': cv2.TM_SQDIFF_NORMED
}

class ImageProcessor:
    def __init__(self):
        self.current_algorithm = 'TM_CCOEFF_NORMED'
        self.color_lower = np.array([0, 0, 0])
        self.color_upper = np.array([255, 255, 255])
        self.enable_color_tracking = False
        self.enable_edge_detection = False
        self.edge_threshold1 = 100
        self.edge_threshold2 = 200

    def set_algorithm(self, algorithm_name):
        if algorithm_name in MATCH_ALGORITHMS:
            self.current_algorithm = algorithm_name

    def match_template(self, screenshot, template):
        try:
            result = cv2.matchTemplate(screenshot, template, MATCH_ALGORITHMS[self.current_algorithm])

            if self.current_algorithm in ['TM_SQDIFF', 'TM_SQDIFF_NORMED']:
                min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
                return max_loc if self.current_algorithm == 'TM_SQDIFF' else min_loc, max_val if self.current_algorithm == 'TM_SQDIFF' else min_val
            else:
                min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
                return max_loc, max_val
        except Exception as e:
            obs.script_log(obs.LOG_ERROR, f"模板匹配错误: {str(e)}")
            return None, 0.0

    def detect_edges(self, image):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, self.edge_threshold1, self.edge_threshold2)
        return edges

    def find_color_regions(self, screenshot):
        hsv = cv2.cvtColor(screenshot, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, self.color_lower, self.color_upper)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if contours:
            largest_contour = max(contours, key=cv2.contourArea)
            x, y, w, h = cv2.boundingRect(largest_contour)
            return (x + w // 2, y + h // 2), w * h
        return None, 0

    def process_frame(self, screenshot, template=None):
        results = {}

        if template is not None:
            pos, confidence = self.match_template(screenshot, template)
            results['template_match'] = (pos, confidence)

        if self.enable_color_tracking:
            color_pos, area = self.find_color_regions(screenshot)
            results['color_track'] = (color_pos, area)

        if self.enable_edge_detection:
            edges = self.detect_edges(screenshot)
            results['edges'] = edges

        return results

image_processor = ImageProcessor()

def script_description():
    return """屏幕内容读取与鼠标控制插件 (暴力模式版)

功能：
1. 屏幕内容捕获（自动持续）
2. 游戏人物追踪（头部/胸口）
3. 鼠标自动追踪目标
4. 多种模板匹配算法
5. 颜色识别与追踪
6. 边缘检测
7. 轨迹平滑与速度控制
8. 暴力模式（极限性能）
9. 警告提示
10. 吸附功能（网格/边缘/中心/元素）"""

def script_defaults(settings):
    obs.obs_data_set_default_bool(settings, "enable_capture", False)
    obs.obs_data_set_default_int(settings, "capture_interval", 50)
    obs.obs_data_set_default_bool(settings, "enable_mouse_control", False)
    obs.obs_data_set_default_int(settings, "target_x", 0)
    obs.obs_data_set_default_int(settings, "target_y", 0)
    obs.obs_data_set_default_string(settings, "tracking_target", "head")
    obs.obs_data_set_default_bool(settings, "enable_tracking", False)
    obs.obs_data_set_default_double(settings, "confidence_threshold", 0.8)
    obs.obs_data_set_default_string(settings, "template_path", "")

    obs.obs_data_set_default_string(settings, "match_algorithm", "TM_CCOEFF_NORMED")
    obs.obs_data_set_default_bool(settings, "enable_color_tracking", False)
    obs.obs_data_set_default_int(settings, "color_h_lower", 0)
    obs.obs_data_set_default_int(settings, "color_h_upper", 180)
    obs.obs_data_set_default_int(settings, "color_s_lower", 0)
    obs.obs_data_set_default_int(settings, "color_s_upper", 255)
    obs.obs_data_set_default_int(settings, "color_v_lower", 0)
    obs.obs_data_set_default_int(settings, "color_v_upper", 255)
    obs.obs_data_set_default_bool(settings, "enable_edge_detection", False)
    obs.obs_data_set_default_int(settings, "edge_threshold1", 100)
    obs.obs_data_set_default_int(settings, "edge_threshold2", 200)

    obs.obs_data_set_default_bool(settings, "enable_smoothing", True)
    obs.obs_data_set_default_double(settings, "smoothing_factor", 0.3)
    obs.obs_data_set_default_bool(settings, "enable_speed_control", False)
    obs.obs_data_set_default_double(settings, "move_speed", 1.0)

    obs.obs_data_set_default_bool(settings, "auto_load_template", False)
    obs.obs_data_set_default_bool(settings, "auto_start_tracking", True)

    obs.obs_data_set_default_bool(settings, "enable_brutal_mode", False)
    obs.obs_data_set_default_bool(settings, "brutal_mode_confirmed", False)

    obs.obs_data_set_default_bool(settings, "enable_snap", False)
    obs.obs_data_set_default_bool(settings, "enable_grid_snap", True)
    obs.obs_data_set_default_bool(settings, "enable_edge_snap", True)
    obs.obs_data_set_default_bool(settings, "enable_center_snap", False)
    obs.obs_data_set_default_bool(settings, "enable_element_snap", False)
    obs.obs_data_set_default_int(settings, "grid_size", 50)
    obs.obs_data_set_default_int(settings, "snap_threshold", 10)
    obs.obs_data_set_default_double(settings, "element_sensitivity", 0.5)
    obs.obs_data_set_default_int(settings, "canvas_width", 1920)
    obs.obs_data_set_default_int(settings, "canvas_height", 1080)

def script_update(settings):
    global script_settings, brutal_mode_active, brutal_mode_warning_shown
    script_settings = settings
    update_processor_settings()
    update_mouse_settings()
    update_snap_settings()
    update_plugin_state()

    enable_brutal = obs.obs_data_get_bool(settings, "enable_brutal_mode")
    if enable_brutal and not brutal_mode_active:
        brutal_mode_confirmed = obs.obs_data_get_bool(settings, "brutal_mode_confirmed")
        if not brutal_mode_confirmed:
            brutal_mode_warning_shown = True
            obs.script_log(obs.LOG_WARNING, "⚠️ 警告：暴力模式即将启用！")
            obs.script_log(obs.LOG_WARNING, "⚠️ 此模式会使用最高性能设置")
            obs.script_log(obs.LOG_WARNING, "⚠️ 请在设置中确认启用")
        else:
            apply_brutal_mode(settings)
    else:
        brutal_mode_active = False

def apply_brutal_mode(settings):
    global brutal_mode_active, brutal_mode_warning_shown
    brutal_mode_active = True
    brutal_mode_warning_shown = False

    obs.obs_data_set_int(settings, "capture_interval", 10)
    obs.obs_data_set_double(settings, "confidence_threshold", 0.5)
    obs.obs_data_set_bool(settings, "enable_color_tracking", True)
    obs.obs_data_set_bool(settings, "enable_edge_detection", True)
    obs.obs_data_set_bool(settings, "enable_smoothing", False)
    obs.obs_data_set_double(settings, "move_speed", 2.0)
    obs.obs_data_set_bool(settings, "enable_speed_control", True)

    obs.script_log(obs.LOG_WARNING, "⚠️ 暴力模式已启用！")
    obs.script_log(obs.LOG_WARNING, "⚠️ 捕获间隔: 10ms | 阈值: 0.5 | 所有追踪已开启")

def update_processor_settings():
    global image_processor, brutal_mode_active

    if not script_settings:
        return

    enable_brutal = obs.obs_data_get_bool(script_settings, "enable_brutal_mode")
    brutal_mode_confirmed = obs.obs_data_get_bool(script_settings, "brutal_mode_confirmed")

    if enable_brutal and brutal_mode_confirmed and not brutal_mode_active:
        apply_brutal_mode(script_settings)
        return

    algorithm = obs.obs_data_get_string(script_settings, "match_algorithm")
    image_processor.set_algorithm(algorithm)

    if not brutal_mode_active:
        image_processor.enable_color_tracking = obs.obs_data_get_bool(script_settings, "enable_color_tracking")
    else:
        image_processor.enable_color_tracking = True

    image_processor.color_lower = np.array([
        obs.obs_data_get_int(script_settings, "color_h_lower"),
        obs.obs_data_get_int(script_settings, "color_s_lower"),
        obs.obs_data_get_int(script_settings, "color_v_lower")
    ])
    image_processor.color_upper = np.array([
        obs.obs_data_get_int(script_settings, "color_h_upper"),
        obs.obs_data_get_int(script_settings, "color_s_upper"),
        obs.obs_data_get_int(script_settings, "color_v_upper")
    ])

    if not brutal_mode_active:
        image_processor.enable_edge_detection = obs.obs_data_get_bool(script_settings, "enable_edge_detection")
    else:
        image_processor.enable_edge_detection = True

    image_processor.edge_threshold1 = obs.obs_data_get_int(script_settings, "edge_threshold1")
    image_processor.edge_threshold2 = obs.obs_data_get_int(script_settings, "edge_threshold2")

def update_mouse_settings():
    global mouse_controller, brutal_mode_active

    if not script_settings:
        return

    if not brutal_mode_active:
        mouse_controller.enable_smoothing = obs.obs_data_get_bool(script_settings, "enable_smoothing")
        mouse_controller.smoothing_factor = obs.obs_data_get_double(script_settings, "smoothing_factor")
        mouse_controller.enable_speed_control = obs.obs_data_get_bool(script_settings, "enable_speed_control")
        mouse_controller.move_speed = obs.obs_data_get_double(script_settings, "move_speed")
    else:
        mouse_controller.enable_smoothing = False
        mouse_controller.enable_speed_control = True
        mouse_controller.move_speed = 2.0

def update_snap_settings():
    global snap_controller

    if not script_settings:
        return

    snap_controller.enable_snap = obs.obs_data_get_bool(script_settings, "enable_snap")
    snap_controller.enable_grid_snap = obs.obs_data_get_bool(script_settings, "enable_grid_snap")
    snap_controller.enable_edge_snap = obs.obs_data_get_bool(script_settings, "enable_edge_snap")
    snap_controller.enable_center_snap = obs.obs_data_get_bool(script_settings, "enable_center_snap")
    snap_controller.enable_element_snap = obs.obs_data_get_bool(script_settings, "enable_element_snap")
    snap_controller.grid_size = obs.obs_data_get_int(script_settings, "grid_size")
    snap_controller.snap_threshold = obs.obs_data_get_int(script_settings, "snap_threshold")
    snap_controller.element_sensitivity = obs.obs_data_get_double(script_settings, "element_sensitivity")

    if snap_controller.enable_snap:
        obs.script_log(obs.LOG_INFO, f"🧲 吸附已启用 | 网格:{snap_controller.enable_grid_snap} 边缘:{snap_controller.enable_edge_snap} 中心:{snap_controller.enable_center_snap} 元素:{snap_controller.enable_element_snap}")
    else:
        obs.script_log(obs.LOG_INFO, "吸附功能已禁用")

def script_properties():
    props = obs.obs_properties_create()

    obs.obs_properties_add_bool(props, "enable_capture", "启用屏幕捕获")
    obs.obs_properties_add_int(props, "capture_interval", "捕获间隔(ms)", 10, 500, 10)

    brutal_group = obs.obs_properties_create()
    obs.obs_properties_add_group(props, "brutal_group", "⚠️ 暴力模式", obs.OBS_GROUP_NORMAL, brutal_group)

    obs.obs_properties_add_bool(brutal_group, "enable_brutal_mode", "启用暴力模式（最高性能）")
    obs.obs_properties_add_bool(brutal_group, "brutal_mode_confirmed", "⚠️ 确认启用暴力模式（风险自负）")

    brutal_desc = obs.obs_properties_add_text(brutal_group, "brutal_warning_text",
        "⚠️ 暴力模式将启用所有功能并设置为极限值\n"
        "⚠️ 捕获间隔: 10ms | 匹配阈值: 0.5\n"
        "⚠️ 颜色追踪: 开启 | 边缘检测: 开启\n"
        "⚠️ 轨迹平滑: 关闭 | 移动速度: 2.0x",
        obs.OBS_TEXT_INFO)
    obs.obs_property_set_enabled(brutal_desc, False)

    auto_group = obs.obs_properties_create()
    obs.obs_properties_add_group(props, "auto_group", "自动追踪设置", obs.OBS_GROUP_NORMAL, auto_group)

    obs.obs_properties_add_bool(auto_group, "auto_start_tracking", "插件加载时自动开始追踪")
    obs.obs_properties_add_bool(auto_group, "auto_load_template", "自动加载模板图片")

    tracking_group = obs.obs_properties_create()
    obs.obs_properties_add_group(props, "tracking_group", "追踪设置", obs.OBS_GROUP_NORMAL, tracking_group)

    obs.obs_properties_add_bool(tracking_group, "enable_tracking", "启用目标追踪")

    target_list = obs.obs_properties_add_list(tracking_group, "tracking_target", "追踪目标",
                                               obs.OBS_COMBO_TYPE_LIST, obs.OBS_COMBO_FORMAT_STRING)
    obs.obs_property_list_add_string(target_list, "头部", "head")
    obs.obs_property_list_add_string(target_list, "胸口", "chest")

    obs.obs_properties_add_double(tracking_group, "confidence_threshold", "匹配阈值", 0.5, 1.0, 0.05)

    obs.obs_properties_add_path(tracking_group, "template_path", "模板图片路径",
                                obs.OBS_PATH_FILE, "图像文件 (*.png *.jpg *.jpeg)", None)

    algorithm_list = obs.obs_properties_add_list(tracking_group, "match_algorithm", "匹配算法",
                                                 obs.OBS_COMBO_TYPE_LIST, obs.OBS_COMBO_FORMAT_STRING)
    for alg_name in MATCH_ALGORITHMS.keys():
        obs.obs_property_list_add_string(algorithm_list, alg_name, alg_name)

    color_group = obs.obs_properties_create()
    obs.obs_properties_add_group(props, "color_group", "颜色追踪", obs.OBS_GROUP_NORMAL, color_group)

    obs.obs_properties_add_bool(color_group, "enable_color_tracking", "启用颜色追踪")
    obs.obs_properties_add_int(color_group, "color_h_lower", "H下界", 0, 180, 1)
    obs.obs_properties_add_int(color_group, "color_h_upper", "H上界", 0, 180, 1)
    obs.obs_properties_add_int(color_group, "color_s_lower", "S下界", 0, 255, 1)
    obs.obs_properties_add_int(color_group, "color_s_upper", "S上界", 0, 255, 1)
    obs.obs_properties_add_int(color_group, "color_v_lower", "V下界", 0, 255, 1)
    obs.obs_properties_add_int(color_group, "color_v_upper", "V上界", 0, 255, 1)

    edge_group = obs.obs_properties_create()
    obs.obs_properties_add_group(props, "edge_group", "边缘检测", obs.OBS_GROUP_NORMAL, edge_group)

    obs.obs_properties_add_bool(edge_group, "enable_edge_detection", "启用边缘检测")
    obs.obs_properties_add_int(edge_group, "edge_threshold1", "阈值1", 50, 200, 10)
    obs.obs_properties_add_int(edge_group, "edge_threshold2", "阈值2", 100, 300, 10)

    mouse_group = obs.obs_properties_create()
    obs.obs_properties_add_group(props, "mouse_group", "鼠标控制", obs.OBS_GROUP_NORMAL, mouse_group)

    obs.obs_properties_add_bool(mouse_group, "enable_mouse_control", "启用鼠标控制")
    obs.obs_properties_add_int(mouse_group, "target_x", "目标X坐标", 0, 3840, 1)
    obs.obs_properties_add_int(mouse_group, "target_y", "目标Y坐标", 0, 2160, 1)
    obs.obs_properties_add_bool(mouse_group, "enable_smoothing", "启用轨迹平滑")
    obs.obs_properties_add_double(mouse_group, "smoothing_factor", "平滑系数", 0.1, 1.0, 0.1)
    obs.obs_properties_add_bool(mouse_group, "enable_speed_control", "启用速度控制")
    obs.obs_properties_add_double(mouse_group, "move_speed", "移动速度", 0.1, 2.0, 0.1)

    button_group = obs.obs_properties_create()
    obs.obs_properties_add_group(props, "button_group", "操作按钮", obs.OBS_GROUP_NORMAL, button_group)

    obs.obs_properties_add_button(button_group, "set_template", "设置当前屏幕为模板", set_template_button_clicked)
    obs.obs_properties_add_button(button_group, "move_mouse", "移动鼠标到目标", move_mouse_button_clicked)
    obs.obs_properties_add_button(button_group, "left_click", "执行左键点击", left_click_button_clicked)
    obs.obs_properties_add_button(button_group, "right_click", "执行右键点击", right_click_button_clicked)

    snap_group = obs.obs_properties_create()
    obs.obs_properties_add_group(props, "snap_group", "🧲 吸附功能", obs.OBS_GROUP_NORMAL, snap_group)

    obs.obs_properties_add_bool(snap_group, "enable_snap", "启用吸附功能")
    obs.obs_properties_add_bool(snap_group, "enable_grid_snap", "启用网格吸附")
    obs.obs_properties_add_int(snap_group, "grid_size", "网格大小(px)", 10, 200, 10)
    obs.obs_properties_add_bool(snap_group, "enable_edge_snap", "启用边缘吸附")
    obs.obs_properties_add_bool(snap_group, "enable_center_snap", "启用中心吸附")
    obs.obs_properties_add_int(snap_group, "snap_threshold", "吸附阈值(px)", 5, 50, 5)

    element_snap_group = obs.obs_properties_create()
    obs.obs_properties_add_group(snap_group, "element_snap_group", "元素吸附（配合屏幕检测）", obs.OBS_GROUP_NORMAL, element_snap_group)

    obs.obs_properties_add_bool(element_snap_group, "enable_element_snap", "启用元素吸附")
    obs.obs_properties_add_double(element_snap_group, "element_sensitivity", "元素灵敏度", 0.3, 1.0, 0.05)

    snap_info = obs.obs_properties_add_text(element_snap_group, "element_snap_info",
        "📌 元素吸附说明：\n"
        "• 自动检测屏幕中的边缘、颜色区域\n"
        "• 配合模板匹配可吸附到目标物体\n"
        "• 灵敏度越高，越容易匹配元素\n"
        "• 建议与追踪功能配合使用",
        obs.OBS_TEXT_INFO)
    obs.obs_property_set_enabled(snap_info, False)

    obs.obs_properties_add_int(snap_group, "canvas_width", "画布宽度", 1280, 7680, 1)
    obs.obs_properties_add_int(snap_group, "canvas_height", "画布高度", 720, 4320, 1)

    obs.obs_properties_add_button(snap_group, "test_snap", "测试吸附", test_snap_button_clicked)

    return props

def script_load(settings):
    global script_settings, target_image, brutal_mode_active
    script_settings = settings

    enable_brutal = obs.obs_data_get_bool(settings, "enable_brutal_mode")
    brutal_mode_confirmed = obs.obs_data_get_bool(settings, "brutal_mode_confirmed")

    if enable_brutal and brutal_mode_confirmed:
        apply_brutal_mode(settings)
        obs.script_log(obs.LOG_WARNING, "⚠️ 暴力模式已启用（上次会话）")

    auto_load = obs.obs_data_get_bool(settings, "auto_load_template")
    if auto_load:
        template_path = obs.obs_data_get_string(settings, "template_path")
        if template_path and os.path.exists(template_path):
            load_template_from_path(template_path)
            obs.script_log(obs.LOG_INFO, f"自动加载模板: {template_path}")

    auto_start = obs.obs_data_get_bool(settings, "auto_start_tracking")
    if auto_start:
        obs.obs_data_set_bool(settings, "enable_capture", True)
        obs.obs_data_set_bool(settings, "enable_tracking", True)
        start_capture()
        obs.script_log(obs.LOG_INFO, "自动开始追踪")

    obs.script_log(obs.LOG_INFO, "屏幕鼠标控制插件(暴力模式版)已加载")

def script_unload():
    global brutal_mode_active, brutal_mode_warning_shown
    brutal_mode_active = False
    brutal_mode_warning_shown = False
    stop_capture()
    obs.script_log(obs.LOG_INFO, "屏幕鼠标控制插件(暴力模式版)已卸载")

def update_plugin_state():
    if not script_settings:
        return

    enable_capture = obs.obs_data_get_bool(script_settings, "enable_capture")

    if enable_capture and not is_running:
        start_capture()
    elif not enable_capture and is_running:
        stop_capture()

def start_capture():
    global is_running, capture_thread

    if is_running:
        return

    is_running = True
    capture_thread = threading.Thread(target=capture_loop, daemon=True)
    capture_thread.start()

    obs.script_log(obs.LOG_INFO, "屏幕捕获已启动")

def stop_capture():
    global is_running, tracking_active

    if not is_running:
        return

    is_running = False
    tracking_active = False
    obs.script_log(obs.LOG_INFO, "屏幕捕获已停止")

def capture_loop():
    global tracking_active

    while is_running:
        try:
            interval = obs.obs_data_get_int(script_settings, "capture_interval") / 1000.0
            capture_screen()
            time.sleep(interval)
        except Exception as e:
            obs.script_log(obs.LOG_ERROR, f"捕获循环错误: {str(e)}")
            break

def capture_screen():
    global target_image, tracking_active, brutal_mode_active

    try:
        screenshot = pyautogui.screenshot()
        screenshot_np = np.array(screenshot)
        screenshot_bgr = cv2.cvtColor(screenshot_np, cv2.COLOR_RGB2BGR)

        frame_queue.append(screenshot_bgr)

        screen_size = pyautogui.size()
        mouse_pos = pyautogui.position()

        results = image_processor.process_frame(screenshot_bgr, target_image)

        tracked_pos = None
        confidence = 0.0

        if 'template_match' in results:
            pos, confidence = results['template_match']
            threshold = 0.5 if brutal_mode_active else obs.obs_data_get_double(script_settings, "confidence_threshold")
            if pos is not None and confidence >= threshold:
                h, w = target_image.shape[:2]
                center_x, center_y = pos[0] + w // 2, pos[1] + h // 2

                tracking_target = obs.obs_data_get_string(script_settings, "tracking_target")
                if tracking_target == "chest":
                    center_y += int(h * 0.3)

                tracked_pos = (center_x, center_y)
                tracking_active = True

        if image_processor.enable_color_tracking and 'color_track' in results:
            color_pos, area = results['color_track']
            if color_pos is not None and area > 100:
                tracked_pos = color_pos
                tracking_active = True

        if snap_controller.enable_element_snap:
            snap_controller.detect_elements(screenshot_bgr, target_image)
            if snap_controller.detected_elements:
                obs.script_log(obs.LOG_DEBUG, f"🧲 检测到 {len(snap_controller.detected_elements)} 个元素")

        if tracked_pos is not None:
            enable_mouse_control = obs.obs_data_get_bool(script_settings, "enable_mouse_control")

            if snap_controller.enable_snap:
                canvas_width = obs.obs_data_get_int(script_settings, "canvas_width")
                canvas_height = obs.obs_data_get_int(script_settings, "canvas_height")
                final_x, final_y = snap_controller.apply_snap(
                    tracked_pos[0], tracked_pos[1],
                    0, 0, canvas_width, canvas_height,
                    target_pos=tracked_pos
                )
            else:
                final_x, final_y = tracked_pos

            if enable_mouse_control:
                mouse_controller.move_to_smooth(final_x, final_y)
            mode_tag = "[暴力模式] " if brutal_mode_active else ""
            snap_tag = " 🧲吸附" if snap_controller.enable_snap and snap_controller.enable_element_snap else ""
            obs.script_log(obs.LOG_DEBUG, f"{mode_tag}追踪位置: ({final_x}, {final_y}) 置信度: {confidence:.2f}{snap_tag}")
        else:
            obs.script_log(obs.LOG_DEBUG, f"未检测到目标 | 屏幕: {screen_size[0]}x{screen_size[1]} 鼠标: {mouse_pos}")

    except Exception as e:
        obs.script_log(obs.LOG_ERROR, f"屏幕捕获错误: {str(e)}")

def load_template_from_path(template_path):
    global target_image
    try:
        target_image = cv2.imread(template_path)
        if target_image is not None:
            obs.script_log(obs.LOG_INFO, f"模板已加载: {template_path} ({target_image.shape[1]}x{target_image.shape[0]})")
        else:
            obs.script_log(obs.LOG_ERROR, f"无法读取模板图片: {template_path}")
    except Exception as e:
        obs.script_log(obs.LOG_ERROR, f"加载模板失败: {str(e)}")

def set_template_button_clicked(props, prop):
    global target_image

    try:
        template_path = obs.obs_data_get_string(script_settings, "template_path")

        if template_path and os.path.exists(template_path):
            load_template_from_path(template_path)
        else:
            screenshot = pyautogui.screenshot()
            screenshot_np = np.array(screenshot)
            target_image = cv2.cvtColor(screenshot_np, cv2.COLOR_RGB2BGR)
            obs.script_log(obs.LOG_INFO, "已设置当前屏幕为模板")

        return True
    except Exception as e:
        obs.script_log(obs.LOG_ERROR, f"设置模板错误: {str(e)}")
        return True

def move_mouse_button_clicked(props, prop):
    try:
        enable_mouse_control = obs.obs_data_get_bool(script_settings, "enable_mouse_control")
        target_x = obs.obs_data_get_int(script_settings, "target_x")
        target_y = obs.obs_data_get_int(script_settings, "target_y")

        if enable_mouse_control:
            mouse_controller.move_to_smooth(target_x, target_y)
        else:
            pyautogui.moveTo(target_x, target_y, duration=0.5)

        obs.script_log(obs.LOG_INFO, f"鼠标已移动到: ({target_x}, {target_y})")
    except Exception as e:
        obs.script_log(obs.LOG_ERROR, f"鼠标移动错误: {str(e)}")
    return True

def left_click_button_clicked(props, prop):
    try:
        mouse_controller.click('left')
        obs.script_log(obs.LOG_INFO, "左键点击已执行")
    except Exception as e:
        obs.script_log(obs.LOG_ERROR, f"点击错误: {str(e)}")
    return True

def right_click_button_clicked(props, prop):
    try:
        mouse_controller.right_click()
        obs.script_log(obs.LOG_INFO, "右键点击已执行")
    except Exception as e:
        obs.script_log(obs.LOG_ERROR, f"点击错误: {str(e)}")
    return True

def test_snap_button_clicked(props, prop):
    try:
        if not snap_controller.enable_snap:
            obs.script_log(obs.LOG_WARNING, "🧲 请先启用吸附功能")
            return True

        test_x, test_y = 100, 100
        canvas_width = obs.obs_data_get_int(script_settings, "canvas_width")
        canvas_height = obs.obs_data_get_int(script_settings, "canvas_height")

        snapped_x, snapped_y = snap_controller.apply_snap(
            test_x, test_y, 0, 0, canvas_width, canvas_height
        )

        obs.script_log(obs.LOG_INFO, f"🧲 吸附测试 | 原始: ({test_x}, {test_y}) → 吸附后: ({snapped_x}, {snapped_y})")
        obs.script_log(obs.LOG_INFO, f"🧲 吸附配置 | 网格:{snap_controller.grid_size}px 阈值:{snap_controller.snap_threshold}px 灵敏度:{snap_controller.element_sensitivity}")
        obs.script_log(obs.LOG_INFO, f"🧲 吸附模式 | 网格:{snap_controller.enable_grid_snap} 边缘:{snap_controller.enable_edge_snap} 中心:{snap_controller.enable_center_snap} 元素:{snap_controller.enable_element_snap}")

        if snap_controller.enable_element_snap and target_image is not None:
            obs.script_log(obs.LOG_INFO, "🧲 元素吸附：已加载模板，将检测并吸附到类似元素")

        mouse_controller.move_to_smooth(snapped_x, snapped_y)

    except Exception as e:
        obs.script_log(obs.LOG_ERROR, f"吸附测试错误: {str(e)}")
    return True
