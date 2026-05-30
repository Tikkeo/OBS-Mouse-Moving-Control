import cv2
import numpy as np
import pyautogui
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import threading
import time
import os

class TemplateCaptureTool:
    def __init__(self, root):
        self.root = root
        self.root.title("模板捕获工具 (增强版)")
        self.root.geometry("1000x700")

        self.screenshot = None
        self.template = None
        self.selection_start = None
        self.selection_end = None
        self.is_selecting = False
        self.mouse_pos = (0, 0)

        self.show_edges = False
        self.edge_threshold1 = 100
        self.edge_threshold2 = 200

        self.color_picker_mode = False
        self.picked_colors = []

        self.setup_ui()
        self.bind_events()

    def setup_ui(self):
        toolbar = tk.Frame(self.root, bg="#f0f0f0")
        toolbar.pack(side=tk.TOP, fill=tk.X)

        btn_style = {'padx': 8, 'pady': 5, 'bg': '#e0e0e0'}

        tk.Button(toolbar, text="捕获屏幕", command=self.capture_screen, **btn_style).pack(side=tk.LEFT, padx=3, pady=5)
        tk.Button(toolbar, text="加载图片", command=self.load_image, **btn_style).pack(side=tk.LEFT, padx=3, pady=5)
        tk.Button(toolbar, text="保存模板", command=self.save_template, **btn_style).pack(side=tk.LEFT, padx=3, pady=5)
        tk.Button(toolbar, text="清除选择", command=self.clear_selection, **btn_style).pack(side=tk.LEFT, padx=3, pady=5)

        tk.Frame(toolbar, width=2, bg="#cccccc").pack(side=tk.LEFT, fill=tk.Y, padx=5)

        self.edge_toggle = tk.Button(toolbar, text="边缘预览: 关", command=self.toggle_edge_preview,
                                     bg="#ffdddd", **btn_style)
        self.edge_toggle.pack(side=tk.LEFT, padx=3, pady=5)

        self.color_picker_btn = tk.Button(toolbar, text="颜色选择器", command=self.toggle_color_picker,
                                          bg="#ddffdd", **btn_style)
        self.color_picker_btn.pack(side=tk.LEFT, padx=3, pady=5)

        tk.Button(toolbar, text="复制HSV", command=self.copy_hsv_values, **btn_style).pack(side=tk.LEFT, padx=3, pady=5)
        tk.Button(toolbar, text="清除颜色", command=self.clear_colors, **btn_style).pack(side=tk.LEFT, padx=3, pady=5)

        main_frame = tk.Frame(self.root)
        main_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.canvas = tk.Canvas(main_frame, bg="#404040")
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        info_panel = tk.Frame(main_frame, width=250, bg="#f5f5f5")
        info_panel.pack(side=tk.RIGHT, fill=tk.Y, padx=(5, 0))

        info_title = tk.Label(info_panel, text="📊 截图信息", font=('Arial', 11, 'bold'), bg="#f5f5f5")
        info_title.pack(pady=(10, 5))

        self.info_text = tk.Text(info_panel, width=28, height=6, font=('Consolas', 9),
                                 bg="#ffffff", relief=tk.SUNKEN)
        self.info_text.pack(pady=5, padx=5)
        self.info_text.insert('1.0', "未捕获屏幕")

        coords_title = tk.Label(info_panel, text="📍 鼠标坐标", font=('Arial', 11, 'bold'), bg="#f5f5f5")
        coords_title.pack(pady=(15, 5))

        self.coords_label = tk.Label(info_panel, text="X: 0  Y: 0", font=('Consolas', 12),
                                     bg="#ffffff", relief=tk.SUNKEN, anchor=tk.W)
        self.coords_label.pack(fill=tk.X, padx=5, ipady=5)

        selection_title = tk.Label(info_panel, text="✂️ 框选信息", font=('Arial', 11, 'bold'), bg="#f5f5f5")
        selection_title.pack(pady=(15, 5))

        self.selection_label = tk.Label(info_panel, text="未选择区域", font=('Consolas', 10),
                                        bg="#ffffff", relief=tk.SUNKEN, anchor=tk.W)
        self.selection_label.pack(fill=tk.X, padx=5, ipady=5)

        colors_title = tk.Label(info_panel, text="🎨 已选颜色 (HSV)", font=('Arial', 11, 'bold'), bg="#f5f5f5")
        colors_title.pack(pady=(15, 5))

        self.colors_frame = tk.Frame(info_panel, bg="#f5f5f5")
        self.colors_frame.pack(fill=tk.BOTH, expand=True, padx=5)

        threshold_title = tk.Label(info_panel, text="⚙️ 边缘阈值", font=('Arial', 11, 'bold'), bg="#f5f5f5")
        threshold_title.pack(pady=(15, 5))

        threshold_frame = tk.Frame(info_panel, bg="#f5f5f5")
        threshold_frame.pack(fill=tk.X, padx=5)

        tk.Label(threshold_frame, text="阈值1:", bg="#f5f5f5").grid(row=0, column=0, sticky='w')
        self.threshold1_scale = tk.Scale(threshold_frame, from_=50, to=200, orient=tk.HORIZONTAL,
                                          command=self.update_edge_threshold, length=120)
        self.threshold1_scale.set(100)
        self.threshold1_scale.grid(row=0, column=1, padx=5)

        tk.Label(threshold_frame, text="阈值2:", bg="#f5f5f5").grid(row=1, column=0, sticky='w', pady=(5,0))
        self.threshold2_scale = tk.Scale(threshold_frame, from_=100, to=300, orient=tk.HORIZONTAL,
                                          command=self.update_edge_threshold, length=120)
        self.threshold2_scale.set(200)
        self.threshold2_scale.grid(row=1, column=1, padx=5, pady=(5,0))

        button_frame = tk.Frame(info_panel, bg="#f5f5f5")
        button_frame.pack(pady=15)

        tk.Button(button_frame, text="全屏截图", command=self.fullscreen_capture,
                  bg="#ddeeff", padx=10).pack(side=tk.LEFT, padx=3)

        self.status_label = tk.Label(self.root, text="准备就绪 | 点击'捕获屏幕'开始",
                                    bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)

    def bind_events(self):
        self.canvas.bind("<Motion>", self.on_mouse_move)
        self.canvas.bind("<Button-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)

    def capture_screen(self):
        self.status_label.config(text="正在捕获屏幕...")
        self.root.update()

        self.root.withdraw()
        time.sleep(0.3)

        screenshot = pyautogui.screenshot()
        self.screenshot = np.array(screenshot)
        self.screenshot = cv2.cvtColor(self.screenshot, cv2.COLOR_RGB2BGR)

        self.root.deiconify()

        self.display_image(self.screenshot)
        self.update_screenshot_info()
        self.status_label.config(text="屏幕已捕获 | 拖动鼠标选择模板区域 | Ctrl+点击选择颜色")

    def fullscreen_capture(self):
        self.capture_screen()

    def load_image(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("图像文件", "*.png *.jpg *.jpeg *.bmp"), ("所有文件", "*.*")]
        )
        if file_path:
            self.screenshot = cv2.imread(file_path)
            if self.screenshot is not None:
                self.display_image(self.screenshot)
                self.update_screenshot_info()
                self.status_label.config(text=f"已加载: {os.path.basename(file_path)} | 拖动鼠标选择模板区域")
            else:
                self.status_label.config(text="无法加载图片")

    def display_image(self, img):
        display = img.copy()

        if self.show_edges:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, self.edge_threshold1, self.edge_threshold2)
            display = cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)

        img_rgb = cv2.cvtColor(display, cv2.COLOR_BGR2RGB)
        img_pil = Image.fromarray(img_rgb)

        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()

        if canvas_width > 1 and canvas_height > 1:
            img_pil.thumbnail((canvas_width, canvas_height), Image.LANCZOS)

        self.photo = ImageTk.PhotoImage(img_pil)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.photo)
        self.canvas.image = self.photo

        self.image_width, self.image_height = img_pil.size
        self.original_width, self.original_height = img.shape[1], img.shape[0]

        if self.selection_start and self.selection_end:
            self.draw_selection()

        for i, (x, y) in enumerate(self.picked_colors):
            if x < self.image_width and y < self.image_height:
                scale_x = self.original_width / self.image_width
                scale_y = self.original_height / self.image_height
                real_x = int(x * scale_x)
                real_y = int(y * scale_y)

                b, g, r = self.screenshot[real_y, real_x]
                hsv_val = self.get_hsv_value(real_x, real_y)

                self.canvas.create_oval(x-8, y-8, x+8, y+8,
                                        outline="#00FF00", width=2)
                self.canvas.create_text(x+12, y, text=f"#{i+1}",
                                        fill="#00FF00", font=('Arial', 10, 'bold'))

        self.update_screenshot_info()

    def update_screenshot_info(self):
        if self.screenshot is None:
            self.info_text.delete('1.0', tk.END)
            self.info_text.insert('1.0', "未捕获屏幕")
            return

        h, w = self.screenshot.shape[:2]
        file_size = "N/A"

        info = f"分辨率: {w} x {h}\n"
        info += f"颜色空间: BGR\n"
        info += f"显示缩放: {self.image_width if hasattr(self, 'image_width') else w} x "
        info += f"{self.image_height if hasattr(self, 'image_height') else h}\n"
        info += f"边缘预览: {'开' if self.show_edges else '关'}\n"
        info += f"已选颜色: {len(self.picked_colors)} 个"

        self.info_text.delete('1.0', tk.END)
        self.info_text.insert('1.0', info)

    def get_hsv_value(self, x, y):
        if self.screenshot is None:
            return None
        b, g, r = self.screenshot[y, x]
        pixel = np.uint8([[[b, g, r]]])
        hsv = cv2.cvtColor(pixel, cv2.COLOR_BGR2HSV)
        return hsv[0][0]

    def on_mouse_move(self, event):
        self.mouse_pos = (event.x, event.y)
        self.coords_label.config(text=f"X: {event.x}  Y: {event.y}")

        if self.color_picker_mode and self.screenshot is not None:
            self.canvas.config(cursor="cross")

        if self.selection_start and self.is_selecting:
            self.display_image(self.screenshot)

    def on_mouse_down(self, event):
        if self.screenshot is None:
            return

        if self.color_picker_mode:
            scale_x = self.original_width / self.image_width
            scale_y = self.original_height / self.image_height
            real_x = int(event.x * scale_x)
            real_y = int(event.y * scale_y)

            self.picked_colors.append((event.x, event.y))

            b, g, r = self.screenshot[real_y, real_x]
            hsv_val = self.get_hsv_value(real_x, real_y)

            self.display_image(self.screenshot)
            self.status_label.config(
                text=f"颜色 #{len(self.picked_colors)}: RGB({r},{g},{b}) HSV({hsv_val[0]},{hsv_val[1]},{hsv_val[2]})")
            return

        self.is_selecting = True
        self.selection_start = (event.x, event.y)
        self.selection_end = (event.x, event.y)

    def on_mouse_drag(self, event):
        if not self.is_selecting or self.color_picker_mode:
            return
        self.selection_end = (event.x, event.y)
        self.draw_selection()
        self.update_selection_info()

    def on_mouse_up(self, event):
        if self.color_picker_mode or not self.is_selecting:
            self.is_selecting = False
            return

        self.is_selecting = False
        self.selection_end = (event.x, event.y)
        self.draw_selection()
        self.crop_template()

    def draw_selection(self):
        if self.screenshot is None or self.selection_start is None:
            return

        self.display_image(self.screenshot)

        if self.selection_start and self.selection_end:
            x1, y1 = self.selection_start
            x2, y2 = self.selection_end

            self.canvas.create_rectangle(
                min(x1, x2), min(y1, y2),
                max(x1, x2), max(y1, y2),
                outline="#FF0000", width=2, dash=(5, 3)
            )

            width = abs(x2 - x1)
            height = abs(y2 - y1)
            self.selection_label.config(text=f"起点: ({min(x1,x2)}, {min(y1,y2)})\n"
                                              f"终点: ({max(x1,x2)}, {max(y1,y2)})\n"
                                              f"尺寸: {width} x {height}")

    def update_selection_info(self):
        if self.selection_start and self.selection_end:
            x1, y1 = self.selection_start
            x2, y2 = self.selection_end
            width = abs(x2 - x1)
            height = abs(y2 - y1)
            self.selection_label.config(text=f"起点: ({min(x1,x2)}, {min(y1,y2)})\n"
                                              f"终点: ({max(x1,x2)}, {max(y1,y2)})\n"
                                              f"尺寸: {width} x {height}")

    def crop_template(self):
        if self.screenshot is None or self.selection_start is None or self.selection_end is None:
            return

        x1, y1 = self.selection_start
        x2, y2 = self.selection_end

        scale_x = self.original_width / self.image_width
        scale_y = self.original_height / self.image_height

        real_x1 = int(min(x1, x2) * scale_x)
        real_y1 = int(min(y1, y2) * scale_y)
        real_x2 = int(max(x1, x2) * scale_x)
        real_y2 = int(max(y1, y2) * scale_y)

        real_x1 = max(0, min(real_x1, self.original_width))
        real_y1 = max(0, min(real_y1, self.original_height))
        real_x2 = max(0, min(real_x2, self.original_width))
        real_y2 = max(0, min(real_y2, self.original_height))

        self.template = self.screenshot[real_y1:real_y2, real_x1:real_x2]

        if self.template.size > 0:
            self.status_label.config(text=f"模板已裁剪: {self.template.shape[1]}x{self.template.shape[0]} | 点击'保存模板'保存")
        else:
            self.status_label.config(text="选择区域无效")

    def toggle_edge_preview(self):
        self.show_edges = not self.show_edges
        self.edge_toggle.config(text=f"边缘预览: {'开' if self.show_edges else '关'}",
                                bg="#ddffdd" if self.show_edges else "#ffdddd")
        if self.screenshot is not None:
            self.display_image(self.screenshot)
        self.status_label.config(text=f"边缘预览: {'已开启' if self.show_edges else '已关闭'}")

    def toggle_color_picker(self):
        self.color_picker_mode = not self.color_picker_mode
        self.color_picker_btn.config(text="颜色选择器: ON" if self.color_picker_mode else "颜色选择器",
                                      bg="#aaffaa" if self.color_picker_mode else "#ddffdd")
        self.canvas.config(cursor="cross" if self.color_picker_mode else "")
        self.status_label.config(text="颜色选择器: 点击屏幕选择颜色区域" if self.color_picker_mode
                                else "颜色选择器模式已退出")

    def copy_hsv_values(self):
        if not self.picked_colors or self.screenshot is None:
            self.status_label.config(text="没有选择任何颜色")
            return

        scale_x = self.original_width / self.image_width
        scale_y = self.original_height / self.image_height

        hsv_values = []
        for x, y in self.picked_colors:
            real_x = int(x * scale_x)
            real_y = int(y * scale_y)
            hsv_val = self.get_hsv_value(real_x, real_y)
            if hsv_val is not None:
                hsv_values.append(f"H:{hsv_val[0]} S:{hsv_val[1]} V:{hsv_val[2]}")

        if hsv_values:
            hsv_str = ", ".join(hsv_values)
            self.root.clipboard_clear()
            self.root.clipboard_append(hsv_str)
            self.status_label.config(text=f"已复制HSV值: {hsv_str}")

    def clear_colors(self):
        self.picked_colors = []
        if self.screenshot is not None:
            self.display_image(self.screenshot)
        self.status_label.config(text="已清除所有选择的颜色")

    def update_edge_threshold(self, value):
        self.edge_threshold1 = self.threshold1_scale.get()
        self.edge_threshold2 = self.threshold2_scale.get()
        if self.show_edges and self.screenshot is not None:
            self.display_image(self.screenshot)

    def save_template(self):
        if self.template is None or self.template.size == 0:
            self.status_label.config(text="没有可保存的模板")
            messagebox.showwarning("警告", "请先框选模板区域")
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[
                ("PNG文件", "*.png"),
                ("JPEG文件", "*.jpg"),
                ("BMP文件", "*.bmp"),
                ("所有文件", "*.*")
            ]
        )

        if file_path:
            success = cv2.imwrite(file_path, self.template)
            if success:
                self.status_label.config(text=f"模板已保存到: {file_path}")
                messagebox.showinfo("成功", f"模板已保存到:\n{file_path}")
            else:
                self.status_label.config(text="保存失败")
                messagebox.showerror("错误", "保存模板失败")

    def clear_selection(self):
        self.selection_start = None
        self.selection_end = None
        self.template = None
        if self.screenshot is not None:
            self.display_image(self.screenshot)
        self.selection_label.config(text="未选择区域")
        self.status_label.config(text="选择已清除")

def main():
    root = tk.Tk()
    app = TemplateCaptureTool(root)
    root.mainloop()

if __name__ == "__main__":
    main()
