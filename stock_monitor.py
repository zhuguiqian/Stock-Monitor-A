import sys
import json
import os
import requests
import datetime
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem, 
                             QHeaderView, QMessageBox, QDialog, QLabel, QComboBox, 
                             QLineEdit, QFormLayout, QSpinBox, QListWidget)
from PyQt5.QtCore import QTimer, QThread, pyqtSignal, Qt
from PyQt5.QtGui import QColor, QFont

CONFIG_FILE = "stocks_config.json"

STYLESHEET = """
QMainWindow, QDialog {
    background-color: #1e1e2e;
}
QLabel {
    color: #cdd6f4;
    font-size: 14px;
    font-family: 'Segoe UI', Arial, sans-serif;
}
QPushButton {
    background-color: #89b4fa;
    color: #11111b;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-size: 14px;
    font-weight: bold;
    font-family: 'Segoe UI', Arial, sans-serif;
}
QPushButton:hover {
    background-color: #b4befe;
}
QPushButton:pressed {
    background-color: #74c7ec;
}
QTableWidget {
    background-color: #181825;
    color: #cdd6f4;
    gridline-color: #313244;
    border: 1px solid #313244;
    border-radius: 8px;
    selection-background-color: #45475a;
    font-size: 14px;
    font-family: 'Segoe UI', Arial, sans-serif;
}
QHeaderView::section {
    background-color: #313244;
    color: #cdd6f4;
    padding: 8px;
    border: none;
    border-right: 1px solid #45475a;
    border-bottom: 1px solid #45475a;
    font-weight: bold;
    font-family: 'Segoe UI', Arial, sans-serif;
}
QTableCornerButton::section {
    background-color: #313244;
}
QSpinBox, QComboBox, QLineEdit {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 5px;
    font-size: 14px;
    font-family: 'Segoe UI', Arial, sans-serif;
}
QSpinBox:focus, QComboBox:focus, QLineEdit:focus {
    border: 1px solid #89b4fa;
}
QListWidget {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 4px;
    font-size: 14px;
}
QListWidget::item {
    padding: 5px;
}
QListWidget::item:selected {
    background-color: #89b4fa;
    color: #11111b;
}
QStatusBar {
    color: #a6adc8;
}
"""

def get_stock_prefix(code):
    if code.startswith('6'):
        return 'sh' + code
    elif code.startswith('0') or code.startswith('3'):
        return 'sz' + code
    elif code.startswith('4') or code.startswith('8') or code.startswith('9'):
        return 'bj' + code
    return code

class SearchFetcher(QThread):
    results_fetched = pyqtSignal(list)
    
    def __init__(self, keyword):
        super().__init__()
        self.keyword = keyword
        
    def run(self):
        if not self.keyword:
            self.results_fetched.emit([])
            return
            
        url = f"https://suggest3.sinajs.cn/suggest/type=11,12,13,14,15&key={self.keyword}"
        try:
            res = requests.get(url, timeout=3)
            res.encoding = 'gbk'
            text = res.text.replace('var suggestvalue="', '').replace('";', '')
            results = []
            if text:
                for item in text.split(';'):
                    parts = item.split(',')
                    if len(parts) >= 5:
                        code = parts[2]
                        name = parts[4]
                        results.append({'code': code, 'name': name})
            self.results_fetched.emit(results)
        except:
            self.results_fetched.emit([])

class StockFetcher(QThread):
    data_fetched = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, stocks):
        super().__init__()
        self.stocks = stocks

    def run(self):
        if not self.stocks:
            return
            
        queries = [get_stock_prefix(s['code']) for s in self.stocks]
        url = f"http://qt.gtimg.cn/q={','.join(queries)}"
        
        try:
            response = requests.get(url, timeout=5)
            response.encoding = 'gbk'
            text = response.text
            
            results = {}
            for line in text.strip().split('\n'):
                if not line: continue
                parts = line.split('=')
                if len(parts) == 2:
                    code_part = parts[0].split('_')[-1]
                    code = code_part[2:] if code_part.startswith(('sh', 'sz', 'bj')) else code_part
                    
                    data = parts[1].strip('";').split('~')
                    if len(data) > 30:
                        name = data[1]
                        current_price = float(data[3])
                        yesterday_close = float(data[4])
                        change_percent = float(data[32])
                        
                        results[code] = {
                            'name': name,
                            'price': current_price,
                            'change_percent': change_percent,
                            'yesterday_close': yesterday_close
                        }
            self.data_fetched.emit(results)
        except Exception as e:
            self.error_occurred.emit(str(e))

class AddStockDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("添加自选股")
        self.resize(400, 350)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText("请输入 拼音首字母 / 股票代码 / 股票名称 进行搜索...")
        self.search_input.textChanged.connect(self.on_text_changed)
        layout.addWidget(QLabel("搜索股票:"))
        layout.addWidget(self.search_input)
        
        self.result_list = QListWidget(self)
        self.result_list.itemDoubleClicked.connect(self.on_item_double_clicked)
        layout.addWidget(self.result_list)
        
        btn_layout = QHBoxLayout()
        self.ok_btn = QPushButton("添加选中项", self)
        self.ok_btn.clicked.connect(self.accept_add)
        self.cancel_btn = QPushButton("取消", self)
        self.cancel_btn.setStyleSheet("background-color: #6c7086; color: #11111b;")
        self.cancel_btn.clicked.connect(self.reject)
        
        btn_layout.addWidget(self.ok_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)
        
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self.do_search)
        
        self.selected_code = None
        self.selected_name = None
        self.search_results = []
        
    def on_text_changed(self):
        self.search_timer.start(300)
        
    def do_search(self):
        keyword = self.search_input.text().strip()
        if not keyword:
            self.result_list.clear()
            return
            
        self.fetcher = SearchFetcher(keyword)
        self.fetcher.results_fetched.connect(self.on_results)
        self.fetcher.start()
        
    def on_results(self, results):
        self.search_results = results
        self.result_list.clear()
        for r in results:
            self.result_list.addItem(f"{r['name']} ({r['code']})")
            
    def on_item_double_clicked(self, item):
        self.accept_add()
        
    def accept_add(self):
        row = self.result_list.currentRow()
        if row >= 0 and row < len(self.search_results):
            self.selected_code = self.search_results[row]['code']
            self.selected_name = self.search_results[row]['name']
            self.accept()
        else:
            QMessageBox.warning(self, "提示", "请先在列表中选中一只股票！")
            
    def get_data(self):
        return {
            'code': self.selected_code,
            'name': self.selected_name,
            'alert_type': 0,
            'target': -1
        }

class EditAlertDialog(QDialog):
    def __init__(self, stock_name, stock_code, current_config, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"设置提醒 - {stock_name} ({stock_code})")
        self.resize(380, 200)
        
        layout = QFormLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        self.alert_type = QComboBox(self)
        self.alert_type.addItems(["价格上涨至 (¥) ≥", "价格下跌至 (¥) ≤", "涨幅超过 (%) ≥", "跌幅超过 (%) ≤"])
        self.alert_type.setCurrentIndex(current_config.get('alert_type', 0))
        layout.addRow("提醒条件:", self.alert_type)
        
        self.target_val = QLineEdit(self)
        self.target_val.setPlaceholderText("输入触发提醒的目标数值")
        target = current_config.get('target', -1)
        if target != -1:
            self.target_val.setText(str(target))
        layout.addRow("目标数值:", self.target_val)
        
        btn_layout = QHBoxLayout()
        self.ok_btn = QPushButton("保存设置", self)
        self.ok_btn.clicked.connect(self.accept)
        
        self.disable_btn = QPushButton("停用提醒", self)
        self.disable_btn.setStyleSheet("background-color: #fab387; color: #11111b;")
        self.disable_btn.clicked.connect(self.disable_alert)
        
        self.cancel_btn = QPushButton("取消", self)
        self.cancel_btn.setStyleSheet("background-color: #6c7086; color: #11111b;")
        self.cancel_btn.clicked.connect(self.reject)
        
        btn_layout.addWidget(self.ok_btn)
        btn_layout.addWidget(self.disable_btn)
        btn_layout.addWidget(self.cancel_btn)
        
        layout.addRow("", btn_layout)
        self.is_disabled = False
        
    def disable_alert(self):
        self.is_disabled = True
        self.accept()
        
    def get_data(self):
        if self.is_disabled:
            return {'alert_type': 0, 'target': -1}
            
        target_str = self.target_val.text().strip()
        return {
            'alert_type': self.alert_type.currentIndex(),
            'target': float(target_str) if target_str else -1
        }

class StockMonitorApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.stocks = []
        self.refresh_rate = 60
        self.load_config()
        self.init_ui()
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.fetch_data)
        self.timer.start(self.refresh_rate * 1000)
        
        self.fetch_data()
        
    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.stocks = data.get('stocks', [])
                    self.refresh_rate = data.get('refresh_rate', 60)
            except:
                self.stocks = []
                
    def save_config(self):
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                'stocks': self.stocks,
                'refresh_rate': self.refresh_rate
            }, f, ensure_ascii=False, indent=4)

    def init_ui(self):
        self.setWindowTitle("📈 A股实时行情监测与提醒工具")
        self.resize(950, 550)
        
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)
        
        control_layout = QHBoxLayout()
        
        self.add_btn = QPushButton("➕ 添加股票")
        self.add_btn.clicked.connect(self.add_stock)
        
        self.alert_btn = QPushButton("🔔 设置提醒")
        self.alert_btn.clicked.connect(self.edit_alert)
        self.alert_btn.setStyleSheet("background-color: #cba6f7; color: #11111b;")
        
        self.remove_btn = QPushButton("🗑️ 删除选中")
        self.remove_btn.clicked.connect(self.remove_stock)
        self.remove_btn.setStyleSheet("background-color: #f38ba8; color: #11111b;")
        
        self.refresh_rate_spin = QSpinBox()
        self.refresh_rate_spin.setRange(3, 3600)
        self.refresh_rate_spin.setValue(self.refresh_rate)
        self.refresh_rate_spin.setSuffix(" 秒")
        self.refresh_rate_spin.setMinimumWidth(120)
        self.refresh_rate_spin.valueChanged.connect(self.update_refresh_rate)
        
        control_layout.addWidget(self.add_btn)
        control_layout.addWidget(self.alert_btn)
        control_layout.addWidget(self.remove_btn)
        control_layout.addStretch()
        control_layout.addWidget(QLabel("刷新频率:"))
        control_layout.addWidget(self.refresh_rate_spin)
        
        main_layout.addLayout(control_layout)
        
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["代码", "股票名称", "当前价", "涨跌幅", "提醒条件", "目标值", "状态"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.itemDoubleClicked.connect(self.edit_alert)
        
        main_layout.addWidget(self.table)
        
        self.update_table_display()
        
        self.statusBar().showMessage("系统就绪 - 等待刷新...")

    def update_refresh_rate(self, val):
        self.refresh_rate = val
        self.timer.setInterval(self.refresh_rate * 1000)
        self.save_config()
        self.statusBar().showMessage(f"刷新频率已更新为 {val} 秒")

    def add_stock(self):
        dialog = AddStockDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            data = dialog.get_data()
            if not data['code']: return
            
            for s in self.stocks:
                if s['code'] == data['code']:
                    QMessageBox.warning(self, "提示", "该股票已经在监控列表中！")
                    return
                    
            self.stocks.append(data)
            self.save_config()
            self.update_table_display()
            self.fetch_data()
            
    def edit_alert(self):
        selected = self.table.selectedItems()
        if not selected: 
            QMessageBox.warning(self, "提示", "请先在列表中选中一只股票！")
            return
            
        row = selected[0].row()
        code = self.table.item(row, 0).text()
        name = self.table.item(row, 1).text()
        
        stock_config = next((s for s in self.stocks if s['code'] == code), None)
        if not stock_config: return
        
        dialog = EditAlertDialog(name, code, stock_config, self)
        if dialog.exec_() == QDialog.Accepted:
            try:
                new_data = dialog.get_data()
                stock_config['alert_type'] = new_data['alert_type']
                stock_config['target'] = new_data['target']
                
                self.save_config()
                self.update_table_display()
                self.fetch_data()
            except ValueError:
                QMessageBox.warning(self, "错误", "目标数值格式不正确，请输入数字！")

    def remove_stock(self):
        selected = self.table.selectedItems()
        if not selected: return
        row = selected[0].row()
        code = self.table.item(row, 0).text()
        
        self.stocks = [s for s in self.stocks if s['code'] != code]
        self.save_config()
        self.update_table_display()
        self.fetch_data()

    def update_table_display(self):
        self.table.setRowCount(len(self.stocks))
        alert_types = ["价格上涨至 ≥", "价格下跌至 ≤", "涨幅超过(%) ≥", "跌幅超过(%) ≤"]
        
        for i, stock in enumerate(self.stocks):
            self.table.setItem(i, 0, QTableWidgetItem(stock['code']))
            
            # 使用保存的名字，防止加载出空数据
            name = stock.get('name', '加载中...')
            self.table.setItem(i, 1, QTableWidgetItem(name))
            
            self.table.setItem(i, 2, QTableWidgetItem("--"))
            self.table.setItem(i, 3, QTableWidgetItem("--"))
            
            if stock['target'] == -1:
                self.table.setItem(i, 4, QTableWidgetItem("未设置提醒"))
                self.table.setItem(i, 5, QTableWidgetItem("--"))
            else:
                self.table.setItem(i, 4, QTableWidgetItem(alert_types[stock['alert_type']]))
                self.table.setItem(i, 5, QTableWidgetItem(str(stock['target'])))
            
            status_item = QTableWidgetItem("正在监控")
            status_item.setForeground(QColor('#a6e3a1'))
            self.table.setItem(i, 6, status_item)
            
            # 居中对齐
            for col in range(7):
                item = self.table.item(i, col)
                if item:
                    item.setTextAlignment(Qt.AlignCenter)

    def fetch_data(self):
        if not self.stocks: return
        self.fetcher = StockFetcher(self.stocks)
        self.fetcher.data_fetched.connect(self.on_data_fetched)
        self.fetcher.error_occurred.connect(self.on_fetch_error)
        self.fetcher.start()

    def on_fetch_error(self, err):
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.statusBar().showMessage(f"数据获取失败: {err} | 最近更新: {now_str}")

    def on_data_fetched(self, results):
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.statusBar().showMessage(f"行情数据已更新 - 最新同步时间: {now_str}")
        
        for row in range(self.table.rowCount()):
            code_item = self.table.item(row, 0)
            if not code_item: continue
            code = code_item.text()
            
            if code in results:
                data = results[code]
                
                # 名称 (更新名称)
                name_item = QTableWidgetItem(data['name'])
                name_item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, 1, name_item)
                
                # 价格
                price_item = QTableWidgetItem(f"{data['price']:.2f}")
                price_item.setTextAlignment(Qt.AlignCenter)
                
                # 涨跌幅
                change = data['change_percent']
                change_str = f"{change:+.2f}%"
                change_item = QTableWidgetItem(change_str)
                change_item.setTextAlignment(Qt.AlignCenter)
                
                # 颜色设置：A股红涨绿跌
                color = QColor('#f38ba8') if change > 0 else (QColor('#a6e3a1') if change < 0 else QColor('#cdd6f4'))
                price_item.setForeground(color)
                change_item.setForeground(color)
                
                # 数字加粗
                font = QFont("Segoe UI", 11, QFont.Bold)
                price_item.setFont(font)
                change_item.setFont(font)
                
                self.table.setItem(row, 2, price_item)
                self.table.setItem(row, 3, change_item)
                
                # 检查提醒条件
                stock_config = next((s for s in self.stocks if s['code'] == code), None)
                if stock_config:
                    self.check_alert(stock_config, data, row)

    def check_alert(self, config, data, row):
        alert_type = config['alert_type']
        target = config['target']
        
        if target == -1:
            return 
            
        price = data['price']
        change = data['change_percent']
        name = data['name']
        
        triggered = False
        msg = ""
        
        if alert_type == 0 and price >= target and target > 0:
            triggered = True
            msg = f"📈 【上涨提醒】 {name} ({config['code']}) 价格已上涨至 {price:.2f} 元，达到目标 {target:.2f} 元！"
        elif alert_type == 1 and price <= target and target > 0:
            triggered = True
            msg = f"📉 【下跌提醒】 {name} ({config['code']}) 价格已下跌至 {price:.2f} 元，达到目标 {target:.2f} 元！"
        elif alert_type == 2 and change >= target and target > 0:
            triggered = True
            msg = f"🚀 【暴涨提醒】 {name} ({config['code']}) 涨幅已达 {change:.2f}%，超过设定的 {target:.2f}%！"
        elif alert_type == 3 and change <= -target and target > 0:
            triggered = True
            msg = f"⚠️ 【暴跌提醒】 {name} ({config['code']}) 跌幅已达 {change:.2f}%，超过设定的 -{target:.2f}%！"
            
        if triggered:
            status_item = QTableWidgetItem("🔔 已触发提醒")
            status_item.setForeground(QColor('#f9e2af'))
            status_item.setFont(QFont("Segoe UI", 10, QFont.Bold))
            status_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 6, status_item)
            
            config['target'] = -1
            self.save_config()
            
            target_item = QTableWidgetItem("--")
            target_item.setTextAlignment(Qt.AlignCenter)
            cond_item = QTableWidgetItem("未设置提醒")
            cond_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 4, cond_item)
            self.table.setItem(row, 5, target_item)
            
            alert = QMessageBox(self)
            alert.setWindowFlags(alert.windowFlags() | Qt.WindowStaysOnTopHint)
            alert.setWindowTitle("行情提醒")
            alert.setText(msg)
            alert.setIcon(QMessageBox.Information)
            alert.setStyleSheet(STYLESHEET)
            
            # 强制窗口跳到最前面获取焦点
            alert.show()
            alert.raise_()
            alert.activateWindow()
            alert.exec_()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLESHEET)
    
    window = StockMonitorApp()
    window.show()
    sys.exit(app.exec_())
