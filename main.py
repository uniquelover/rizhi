import os.path
import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QTabWidget, QMenu, QAction, QMessageBox, QWidget
from PyQt5.QtCore import pyqtSlot
from PyQt5.QtGui import QFont
from doip_tool.doip_layout import DoipTool
from log_tool.log_layout import LogPreprocessUI
from lt_tool.lt_tool import LtTool
from mide.ide_script import ScreenCaptureApp
import traceback


def global_excepthook(exc_type, exc_value, exc_traceback):
    if exc_type is ValueError and "null bytes" in str(exc_value):
        print("=" * 60)
        print("捕获到空字节错误，调用栈：")
        traceback.print_exception(exc_type, exc_value, exc_traceback)
        # 尝试打印出问题的字符串片段
        if hasattr(exc_value, 'args') and exc_value.args:
            print("\n错误信息详情：", exc_value.args[0])
        print("=" * 60)
    else:
        sys.__excepthook__(exc_type, exc_value, exc_traceback)


sys.excepthook = global_excepthook


class MainApplication(QMainWindow):
    def __init__(self):
        super().__init__()
        self.tab_index = {}
        self.tab_themes = {
            0: {
                "start": "#ffbe98",
                "end": "#ffd56f",
                "hover": "rgba(255, 214, 150, 0.95)",
                "pane_border": "rgba(191, 137, 77, 0.30)",
            },
            1: {
                "start": "#77c8ff",
                "end": "#8de0d2",
                "hover": "rgba(163, 225, 246, 0.95)",
                "pane_border": "rgba(82, 148, 185, 0.30)",
            },
            2: {
                "start": "#79d7b8",
                "end": "#b7e36f",
                "hover": "rgba(176, 232, 171, 0.95)",
                "pane_border": "rgba(93, 160, 117, 0.30)",
            },
            3: {
                "start": "#ff9f9a",
                "end": "#ffcb7d",
                "hover": "rgba(255, 194, 150, 0.95)",
                "pane_border": "rgba(202, 124, 95, 0.30)",
            },
        }
        try:
            self.setWindowTitle("Autolink test tools")
            self.setMinimumSize(1180, 760)
            self._apply_window_style(0)
            menubar = self.menuBar()

            # 帮助菜单
            contactMenu = QMenu("帮助", self)
            emailAction = QAction("电子邮箱", self)
            emailAction.triggered.connect(self.showEmail)
            contactMenu.addAction(emailAction)
            menubar.addMenu(contactMenu)

            # 版本菜单
            versionMenu = QMenu("版本", self)
            versionAction = QAction("更新日志", self)
            versionAction.triggered.connect(self.show_version_log)
            versionMenu.addAction(versionAction)
            menubar.addMenu(versionMenu)

            # 初始化标签页容器
            self.tab_widget = QTabWidget()
            self.tab_widget.setDocumentMode(True)
            self.tab_widget.setMovable(False)
            self.setCentralWidget(self.tab_widget)

            # 添加初始占位符（注意顺序）
            tab_cnt = -1

            tab_cnt += 1
            self.tab_index[tab_cnt] = "log_tool"
            self.tab_widget.addTab(QWidget(), "log_tool")  # 索引1

            tab_cnt += 1
            self.tab_index[tab_cnt] = "doip_tool"
            self.tab_widget.addTab(QWidget(), "doip_tool")  # 索引0

            tab_cnt += 1
            self.tab_index[tab_cnt] = "lt_tool"
            self.tab_widget.addTab(QWidget(), "lt_tool")  # 索引2

            tab_cnt += 1
            self.tab_index[tab_cnt] = "script_tool"
            self.tab_widget.addTab(QWidget(), "script_tool")  # 索引2

            # 存储标签页实例的字典
            self.tab_instances = {0: None, 1: None, 2: None,3:None}
            # 信号绑定
            self.tab_widget.currentChanged.connect(self.on_tab_changed)

            # 初始化窗口尺寸
            self.resize(1360, 860)

            # 通过设置当前索引触发首次加载
            self.tab_widget.setCurrentIndex(0)  # 关键修复点
            self._apply_window_style(0)
            self.on_tab_changed(0)

        except Exception as e:
            QMessageBox.critical(self, "初始化错误", traceback.format_exc())

    def _apply_window_style(self, active_index):
        theme = self.tab_themes.get(active_index, self.tab_themes[0])
        self.setFont(QFont("Microsoft YaHei UI", 10))
        style = """
            QMainWindow {{
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 #fff3dd,
                    stop: 0.28 #f9d8c2,
                    stop: 0.62 #d9eadf,
                    stop: 1 #bfd7ea
                );
            }}
            QMenuBar {{
                background: rgba(255, 248, 240, 0.88);
                color: #2a3138;
                border-bottom: 1px solid rgba(167, 121, 95, 0.22);
                padding: 8px 12px;
                font-size: 13px;
            }}
            QMenuBar::item {{
                background: transparent;
                padding: 9px 16px;
                margin: 0 5px;
                border-radius: 10px;
            }}
            QMenuBar::item:selected {{
                background: #ffd8b8;
                color: #1f2d30;
            }}
            QMenu {{
                background: #fffaf4;
                color: #2f3b3f;
                border: 1px solid rgba(171, 132, 100, 0.3);
                padding: 8px;
            }}
            QMenu::item {{
                padding: 8px 24px;
                border-radius: 8px;
            }}
            QMenu::item:selected {{
                background: #d8ede4;
            }}
            QTabWidget::pane {{
                border: 1px solid __PANE_BORDER__;
                border-radius: 22px;
                background: rgba(255, 252, 247, 0.9);
                margin-top: 18px;
            }}
            QTabBar::tab {{
                background: rgba(255, 229, 204, 0.75);
                color: #51585d;
                border: 1px solid rgba(174, 124, 93, 0.15);
                padding: 13px 26px;
                margin-right: 10px;
                border-top-left-radius: 14px;
                border-top-right-radius: 14px;
                min-width: 144px;
                font-size: 13px;
                font-weight: 700;
            }}
            QTabBar::tab:selected {{
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 __TAB_START__,
                    stop: 1 __TAB_END__
                );
                color: #203338;
                border-color: rgba(74, 118, 122, 0.32);
            }}
            QTabBar::tab:hover:!selected {{
                background: __TAB_HOVER__;
                color: #243438;
            }}
            QPushButton {{
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 #ffb68a,
                    stop: 1 #66c7b4
                );
                color: #1f2b30;
                border: 1px solid rgba(72, 118, 116, 0.18);
                border-radius: 10px;
                padding: 8px 16px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 #ffcb9b,
                    stop: 1 #7fd7c2
                );
            }}
            QPushButton:pressed {{
                background: #efb183;
            }}
            QLineEdit, QComboBox, QPlainTextEdit, QListWidget, QTableWidget {{
                background: rgba(255, 255, 255, 0.86);
                color: #243438;
                border: 1px solid rgba(111, 136, 145, 0.22);
                border-radius: 10px;
                padding: 6px 10px;
                selection-background-color: #9fd3c7;
                selection-color: #203338;
            }}
            QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QListWidget:focus, QTableWidget:focus {{
                border: 1px solid rgba(90, 170, 160, 0.55);
                background: rgba(255, 255, 255, 0.95);
            }}
            QComboBox::drop-down {{
                border: none;
                width: 26px;
            }}
            QGroupBox {{
                border: 1px solid rgba(102, 132, 142, 0.22);
                border-radius: 16px;
                margin-top: 16px;
                padding-top: 14px;
                background: rgba(255, 250, 243, 0.5);
                color: #314045;
                font-weight: 700;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 14px;
                padding: 0 8px;
                color: #45636d;
            }}
            QCheckBox {{
                color: #304045;
                spacing: 8px;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border-radius: 4px;
                border: 1px solid rgba(95, 142, 138, 0.4);
                background: rgba(255, 255, 255, 0.9);
            }}
            QCheckBox::indicator:checked {{
                background: #66c7b4;
                border-color: #55ad9c;
            }}
            QMessageBox {{
                background: #fffaf4;
            }}
            QLabel, QPushButton, QLineEdit, QComboBox, QCheckBox, QGroupBox, QPlainTextEdit, QListWidget, QTableWidget {{
                font-family: "Microsoft YaHei UI";
            }}
        """
        style = style.replace("__PANE_BORDER__", theme["pane_border"])
        style = style.replace("__TAB_START__", theme["start"])
        style = style.replace("__TAB_END__", theme["end"])
        style = style.replace("__TAB_HOVER__", theme["hover"])
        self.setStyleSheet(style)

    @pyqtSlot(int)
    def on_tab_changed(self, index):
        """动态加载标签页内容的逻辑"""
        if index < 0 or index >= self.tab_widget.count():
            return
        self._apply_window_style(index)

        # 如果当前标签页尚未初始化
        if self.tab_instances[index] is None:
            # 保存原标签标题
            original_tab_text = self.tab_widget.tabText(index)
            name = self.tab_index[index]
            if name == 'doip_tool':
                instance = DoipTool()
            elif name == 'log_tool':
                instance = LogPreprocessUI()
            elif name == 'lt_tool':
                instance = LtTool()
            elif name == 'script_tool':
                instance = ScreenCaptureApp()
            else:
                return None

            # 防止信号递归触发（关键修复点）
            self.tab_widget.currentChanged.disconnect(self.on_tab_changed)
            try:
                # 替换占位符
                self.tab_widget.removeTab(index)
                self.tab_widget.insertTab(index, instance, original_tab_text)
                self.tab_instances[index] = instance
                self.tab_widget.setCurrentIndex(index)
            finally:
                # 确保信号重新连接
                self.tab_widget.currentChanged.connect(self.on_tab_changed)

    def showEmail(self):
        """显示联系邮箱"""
        email = "wangquanbao@auto-link.com.cn"
        QMessageBox.information(self, "联系方式", f"技术支持邮箱: {email}")

    def show_version_log(self):
        """显示版本更新日志"""
        from frozen_dir import app_path
        from PyQt5.QtCore import QUrl
        from PyQt5.QtGui import QDesktopServices

        log_path = f'{app_path}/config/mody.txt'
        file_url = QUrl.fromLocalFile(log_path)

        if not QDesktopServices.openUrl(file_url):
            QMessageBox.warning(self, "打开失败", f"无法找到日志文件:\n{log_path}")


if __name__ == '__main__':

    ## 设置使用的期限
    # from utils.pay import com_big
    # from utils.log_util import format_time
    # t1 = "25-12-21_19-32-01"
    # t2 = format_time()
    # if com_big(t2, t1):
    #     raise Exception('超过使用期限')

    app = QApplication(sys.argv)
    window = MainApplication()
    window.show()
    sys.exit(app.exec_())
