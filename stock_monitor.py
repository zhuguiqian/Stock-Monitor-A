import sys
import json
import os
import requests
import datetime
import smtplib
import ssl
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem, 
                             QHeaderView, QMessageBox, QDialog, QLabel, QComboBox, 
                             QLineEdit, QFormLayout, QSpinBox, QListWidget, QCheckBox)
from PyQt5.QtCore import QTimer, QThread, pyqtSignal, Qt
from PyQt5.QtGui import QColor, QFont

CONFIG_FILE = "stocks_config.json"
EMAIL_CONFIG_FILE = "email_config.json"

ALERT_TYPES = ["价格上涨至 ≥", "价格下跌至 ≤", "涨幅超过(%) ≥", "跌幅超过(%) ≤"]
ALERT_DIALOG_TYPES = ["价格上涨至 (¥) ≥", "价格下跌至 (¥) ≤", "涨幅超过 (%) ≥", "跌幅超过 (%) ≤"]
MARKET_MORNING_OPEN = datetime.time(9, 30)
MARKET_MORNING_CLOSE = datetime.time(11, 30)
MARKET_AFTERNOON_OPEN = datetime.time(13, 0)
MARKET_AFTERNOON_CLOSE = datetime.time(15, 0)

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

def normalize_alert(alert):
    return {
        'alert_type': int(alert.get('alert_type', 0)),
        'target': float(alert.get('target', -1)),
        'email_enabled': bool(alert.get('email_enabled', False)),
        'active': bool(alert.get('active', True)),
        'triggered_at': alert.get('triggered_at', '')
    }

def alert_to_text(alert):
    alert_type = alert.get('alert_type', 0)
    label = ALERT_TYPES[alert_type] if 0 <= alert_type < len(ALERT_TYPES) else "未知条件"
    email_text = "邮件" if alert.get('email_enabled') else "仅弹窗"
    status_text = "" if alert.get('active', True) else " / 已停用"
    return f"{label} {alert.get('target', -1):g} ({email_text}{status_text})"

def next_trading_day_open(now):
    candidate = now + datetime.timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += datetime.timedelta(days=1)
    return datetime.datetime.combine(candidate.date(), MARKET_MORNING_OPEN)

def get_market_status(now=None):
    now = now or datetime.datetime.now()
    today = now.date()
    current_time = now.time()

    if now.weekday() >= 5:
        return {
            'is_open': False,
            'label': '周末休市',
            'next_open': next_trading_day_open(now)
        }

    morning_open = datetime.datetime.combine(today, MARKET_MORNING_OPEN)
    afternoon_open = datetime.datetime.combine(today, MARKET_AFTERNOON_OPEN)

    if current_time < MARKET_MORNING_OPEN:
        return {
            'is_open': False,
            'label': '未开盘',
            'next_open': morning_open
        }
    if MARKET_MORNING_OPEN <= current_time < MARKET_MORNING_CLOSE:
        return {'is_open': True, 'label': '交易中', 'next_open': None}
    if MARKET_MORNING_CLOSE <= current_time < MARKET_AFTERNOON_OPEN:
        return {
            'is_open': False,
            'label': '午间休市',
            'next_open': afternoon_open
        }
    if MARKET_AFTERNOON_OPEN <= current_time < MARKET_AFTERNOON_CLOSE:
        return {'is_open': True, 'label': '交易中', 'next_open': None}
    return {
        'is_open': False,
        'label': '已停盘',
        'next_open': next_trading_day_open(now)
    }

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

class EmailSender(QThread):
    email_sent = pyqtSignal()
    email_failed = pyqtSignal(str)

    def __init__(self, email_config, subject, body, parent=None):
        super().__init__(parent)
        self.email_config = dict(email_config)
        self.subject = subject
        self.body = body

    def run(self):
        try:
            recipients = self._parse_recipients(self.email_config.get('recipients', ''))
            smtp_server = self.email_config.get('smtp_server', '').strip()
            sender = self.email_config.get('sender', '').strip()
            password = self._get_password()
            port = int(self.email_config.get('smtp_port', 465))
            security = self.email_config.get('security', 'ssl')

            if not smtp_server or not sender or not recipients:
                raise ValueError("邮件配置不完整，请检查 SMTP 服务器、发件邮箱和收件人。")

            message = MIMEText(self.body, 'plain', 'utf-8')
            message['From'] = sender
            message['To'] = ', '.join(recipients)
            message['Subject'] = Header(self.subject, 'utf-8').encode()
            message['Date'] = formatdate(localtime=True)
            message['Message-ID'] = make_msgid(domain=sender.split('@')[-1] if '@' in sender else None)

            context = ssl.create_default_context()
            if security == 'ssl':
                with smtplib.SMTP_SSL(smtp_server, port, timeout=12, context=context) as server:
                    self._login_if_needed(server, sender, password)
                    server.sendmail(sender, recipients, message.as_string())
            else:
                with smtplib.SMTP(smtp_server, port, timeout=12) as server:
                    server.ehlo()
                    if security == 'starttls':
                        server.starttls(context=context)
                        server.ehlo()
                    self._login_if_needed(server, sender, password)
                    server.sendmail(sender, recipients, message.as_string())

            self.email_sent.emit()
        except Exception as e:
            self.email_failed.emit(str(e))

    def _get_password(self):
        password_env = self.email_config.get('password_env', '').strip()
        if password_env:
            return os.environ.get(password_env) or self.email_config.get('password', '')
        return self.email_config.get('password', '')

    def _login_if_needed(self, server, sender, password):
        if password:
            server.login(sender, password)

    def _parse_recipients(self, recipients):
        if isinstance(recipients, list):
            return [item.strip() for item in recipients if item and item.strip()]
        return [item.strip() for item in str(recipients).replace(';', ',').split(',') if item.strip()]

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
            'hidden': False,
            'alerts': []
        }

class EditAlertDialog(QDialog):
    def __init__(self, stock_name, stock_code, current_config, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"管理提醒 - {stock_name} ({stock_code})")
        self.resize(520, 420)
        self.alerts = [normalize_alert(alert) for alert in current_config.get('alerts', [])]

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        layout.addWidget(QLabel("提醒列表:"))
        self.alert_list = QListWidget(self)
        self.alert_list.currentRowChanged.connect(self.on_alert_selected)
        layout.addWidget(self.alert_list)

        form_layout = QFormLayout()
        form_layout.setSpacing(12)

        self.alert_type = QComboBox(self)
        self.alert_type.addItems(ALERT_DIALOG_TYPES)
        form_layout.addRow("提醒条件:", self.alert_type)

        self.target_val = QLineEdit(self)
        self.target_val.setPlaceholderText("输入触发提醒的目标数值")
        form_layout.addRow("目标数值:", self.target_val)

        self.email_enabled = QCheckBox("触发这条提醒时发送邮件", self)
        form_layout.addRow("", self.email_enabled)
        layout.addLayout(form_layout)

        edit_btn_layout = QHBoxLayout()
        self.add_alert_btn = QPushButton("新增提醒", self)
        self.add_alert_btn.clicked.connect(self.add_alert)

        self.update_alert_btn = QPushButton("更新选中", self)
        self.update_alert_btn.clicked.connect(self.update_alert)
        self.update_alert_btn.setStyleSheet("background-color: #cba6f7; color: #11111b;")

        self.delete_alert_btn = QPushButton("删除选中", self)
        self.delete_alert_btn.clicked.connect(self.delete_alert)
        self.delete_alert_btn.setStyleSheet("background-color: #f38ba8; color: #11111b;")

        edit_btn_layout.addWidget(self.add_alert_btn)
        edit_btn_layout.addWidget(self.update_alert_btn)
        edit_btn_layout.addWidget(self.delete_alert_btn)
        layout.addLayout(edit_btn_layout)

        btn_layout = QHBoxLayout()
        self.ok_btn = QPushButton("保存并关闭", self)
        self.ok_btn.clicked.connect(self.accept)

        self.cancel_btn = QPushButton("取消", self)
        self.cancel_btn.setStyleSheet("background-color: #6c7086; color: #11111b;")
        self.cancel_btn.clicked.connect(self.reject)

        btn_layout.addWidget(self.ok_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

        self.refresh_alert_list()

    def refresh_alert_list(self):
        current_row = self.alert_list.currentRow()
        self.alert_list.clear()
        for alert in self.alerts:
            self.alert_list.addItem(alert_to_text(alert))
        if self.alerts:
            self.alert_list.setCurrentRow(min(max(current_row, 0), len(self.alerts) - 1))

    def on_alert_selected(self, row):
        if row < 0 or row >= len(self.alerts):
            return
        alert = self.alerts[row]
        self.alert_type.setCurrentIndex(alert.get('alert_type', 0))
        self.target_val.setText(f"{alert.get('target', -1):g}")
        self.email_enabled.setChecked(bool(alert.get('email_enabled', False)))

    def read_form_alert(self):
        target_str = self.target_val.text().strip()
        if not target_str:
            raise ValueError("请输入目标数值")
        target = float(target_str)
        if target <= 0:
            raise ValueError("目标数值必须大于 0")
        return {
            'alert_type': self.alert_type.currentIndex(),
            'target': target,
            'email_enabled': self.email_enabled.isChecked(),
            'active': True,
            'triggered_at': ''
        }

    def add_alert(self):
        try:
            self.alerts.append(self.read_form_alert())
            self.refresh_alert_list()
            self.alert_list.setCurrentRow(len(self.alerts) - 1)
        except ValueError as e:
            QMessageBox.warning(self, "错误", str(e))

    def update_alert(self):
        row = self.alert_list.currentRow()
        if row < 0 or row >= len(self.alerts):
            QMessageBox.warning(self, "提示", "请先选中一条提醒。")
            return
        try:
            self.alerts[row] = self.read_form_alert()
            self.refresh_alert_list()
            self.alert_list.setCurrentRow(row)
        except ValueError as e:
            QMessageBox.warning(self, "错误", str(e))

    def delete_alert(self):
        row = self.alert_list.currentRow()
        if row < 0 or row >= len(self.alerts):
            QMessageBox.warning(self, "提示", "请先选中一条提醒。")
            return
        del self.alerts[row]
        self.refresh_alert_list()

    def get_data(self):
        return [normalize_alert(alert) for alert in self.alerts]

class EmailSettingsDialog(QDialog):
    def __init__(self, email_config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("邮件通知设置")
        self.resize(460, 360)
        self.email_config = dict(email_config)

        layout = QFormLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        self.enabled = QCheckBox("启用邮件通知", self)
        self.enabled.setChecked(bool(self.email_config.get('enabled', False)))
        layout.addRow("", self.enabled)

        self.smtp_server = QLineEdit(self)
        self.smtp_server.setPlaceholderText("例如 smtp.qq.com / smtp.163.com")
        self.smtp_server.setText(self.email_config.get('smtp_server', ''))
        layout.addRow("SMTP 服务器:", self.smtp_server)

        self.smtp_port = QSpinBox(self)
        self.smtp_port.setRange(1, 65535)
        self.smtp_port.setValue(int(self.email_config.get('smtp_port', 465)))
        layout.addRow("SMTP 端口:", self.smtp_port)

        self.security = QComboBox(self)
        self.security.addItem("SSL/TLS", "ssl")
        self.security.addItem("STARTTLS", "starttls")
        self.security.addItem("不加密", "none")
        current_security = self.email_config.get('security', 'ssl')
        security_index = self.security.findData(current_security)
        self.security.setCurrentIndex(security_index if security_index >= 0 else 0)
        self.security.currentIndexChanged.connect(self.on_security_changed)
        layout.addRow("连接安全:", self.security)

        self.sender = QLineEdit(self)
        self.sender.setPlaceholderText("发件邮箱")
        self.sender.setText(self.email_config.get('sender', ''))
        layout.addRow("发件邮箱:", self.sender)

        self.password = QLineEdit(self)
        self.password.setEchoMode(QLineEdit.Password)
        self.password.setPlaceholderText("邮箱授权码；留空则保留原值")
        layout.addRow("授权码:", self.password)

        self.password_env = QLineEdit(self)
        self.password_env.setPlaceholderText("可选，例如 STOCK_MONITOR_EMAIL_PASSWORD")
        self.password_env.setText(self.email_config.get('password_env', ''))
        layout.addRow("授权码环境变量:", self.password_env)

        self.recipients = QLineEdit(self)
        self.recipients.setPlaceholderText("多个收件人用逗号分隔")
        recipients = self.email_config.get('recipients', '')
        self.recipients.setText(', '.join(recipients) if isinstance(recipients, list) else str(recipients))
        layout.addRow("收件人:", self.recipients)

        self.subject_prefix = QLineEdit(self)
        self.subject_prefix.setText(self.email_config.get('subject_prefix', 'A股行情提醒'))
        layout.addRow("邮件标题前缀:", self.subject_prefix)

        btn_layout = QHBoxLayout()
        self.ok_btn = QPushButton("保存设置", self)
        self.ok_btn.clicked.connect(self.accept)

        self.cancel_btn = QPushButton("取消", self)
        self.cancel_btn.setStyleSheet("background-color: #6c7086; color: #11111b;")
        self.cancel_btn.clicked.connect(self.reject)

        btn_layout.addWidget(self.ok_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addRow("", btn_layout)

    def on_security_changed(self):
        security = self.security.currentData()
        if security == 'ssl':
            self.smtp_port.setValue(465)
        elif security == 'starttls':
            self.smtp_port.setValue(587)
        elif security == 'none':
            self.smtp_port.setValue(25)

    def get_data(self):
        password = self.password.text().strip() or self.email_config.get('password', '')
        return {
            'enabled': self.enabled.isChecked(),
            'smtp_server': self.smtp_server.text().strip(),
            'smtp_port': int(self.smtp_port.value()),
            'security': self.security.currentData() or 'ssl',
            'sender': self.sender.text().strip(),
            'password': password,
            'password_env': self.password_env.text().strip(),
            'recipients': self.recipients.text().strip(),
            'subject_prefix': self.subject_prefix.text().strip() or 'A股行情提醒'
        }

class StockMonitorApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.stocks = []
        self.displayed_stocks = []
        self.show_hidden_stocks = False
        self.refresh_rate = 60
        self.email_config = self.default_email_config()
        self.email_workers = []
        self.load_config()
        self.init_ui()
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.fetch_data)
        self.timer.start(self.refresh_rate * 1000)
        
        self.fetch_data()
        
    def default_email_config(self):
        return {
            'enabled': False,
            'smtp_server': '',
            'smtp_port': 465,
            'security': 'ssl',
            'sender': '',
            'password': '',
            'password_env': '',
            'recipients': '',
            'subject_prefix': 'A股行情提醒'
        }

    def normalize_email_config(self, email_config):
        normalized = self.default_email_config()
        if isinstance(email_config, dict):
            normalized.update(email_config)
            if 'security' not in email_config and 'use_ssl' in email_config:
                normalized['security'] = 'ssl' if email_config.get('use_ssl') else 'starttls'
        return normalized

    def normalize_stock_config(self, stock):
        normalized = {
            'code': stock.get('code', ''),
            'name': stock.get('name', ''),
            'hidden': bool(stock.get('hidden', False)),
            'alerts': []
        }

        if isinstance(stock.get('alerts'), list):
            normalized['alerts'] = [normalize_alert(alert) for alert in stock.get('alerts', [])]
        else:
            legacy_target = float(stock.get('target', -1))
            if legacy_target != -1:
                normalized['alerts'] = [normalize_alert({
                    'alert_type': stock.get('alert_type', 0),
                    'target': legacy_target,
                    'email_enabled': False,
                    'active': True
                })]
        return normalized

    def load_email_config(self):
        if not os.path.exists(EMAIL_CONFIG_FILE):
            return
        try:
            with open(EMAIL_CONFIG_FILE, 'r', encoding='utf-8') as f:
                self.email_config = self.normalize_email_config(json.load(f))
        except:
            self.email_config = self.default_email_config()

    def save_email_config(self):
        with open(EMAIL_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.email_config, f, ensure_ascii=False, indent=4)

    def load_config(self):
        legacy_email_config = None
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.stocks = [self.normalize_stock_config(stock) for stock in data.get('stocks', [])]
                    self.refresh_rate = data.get('refresh_rate', 60)
                    if 'email' in data:
                        legacy_email_config = data.get('email', {})
                        self.email_config = self.normalize_email_config(legacy_email_config)
            except:
                self.stocks = []
                self.email_config = self.default_email_config()

        if os.path.exists(EMAIL_CONFIG_FILE):
            self.load_email_config()
        elif legacy_email_config:
            self.save_email_config()

        if legacy_email_config:
            self.save_config()
                
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

        self.hide_btn = QPushButton("隐藏选中")
        self.hide_btn.clicked.connect(self.toggle_selected_stock_hidden)
        self.hide_btn.setStyleSheet("background-color: #fab387; color: #11111b;")

        self.email_btn = QPushButton("✉️ 邮件设置")
        self.email_btn.clicked.connect(self.edit_email_settings)
        self.email_btn.setStyleSheet("background-color: #a6e3a1; color: #11111b;")

        self.show_hidden_check = QCheckBox("显示隐藏股票")
        self.show_hidden_check.setChecked(self.show_hidden_stocks)
        self.show_hidden_check.stateChanged.connect(self.on_show_hidden_changed)
        
        self.refresh_rate_spin = QSpinBox()
        self.refresh_rate_spin.setRange(3, 3600)
        self.refresh_rate_spin.setValue(self.refresh_rate)
        self.refresh_rate_spin.setSuffix(" 秒")
        self.refresh_rate_spin.setMinimumWidth(120)
        self.refresh_rate_spin.valueChanged.connect(self.update_refresh_rate)
        
        control_layout.addWidget(self.add_btn)
        control_layout.addWidget(self.alert_btn)
        control_layout.addWidget(self.remove_btn)
        control_layout.addWidget(self.hide_btn)
        control_layout.addWidget(self.email_btn)
        control_layout.addWidget(self.show_hidden_check)
        control_layout.addStretch()
        control_layout.addWidget(QLabel("刷新频率:"))
        control_layout.addWidget(self.refresh_rate_spin)
        
        main_layout.addLayout(control_layout)
        
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["代码", "股票名称", "当前价", "涨跌幅", "提醒条件", "状态"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.itemDoubleClicked.connect(self.edit_alert)
        self.table.itemSelectionChanged.connect(self.update_hide_button_text)
        
        main_layout.addWidget(self.table)
        
        self.update_table_display()
        
        self.statusBar().showMessage("系统就绪 - 等待刷新...")

    def update_refresh_rate(self, val):
        self.refresh_rate = val
        if get_market_status()['is_open']:
            self.timer.setInterval(self.refresh_rate * 1000)
        self.save_config()
        self.statusBar().showMessage(f"刷新频率已更新为 {val} 秒")

    def get_visible_stocks(self):
        return [stock for stock in self.stocks if self.show_hidden_stocks or not stock.get('hidden', False)]

    def get_selected_stock(self):
        selected = self.table.selectedItems()
        if not selected:
            return None
        row = selected[0].row()
        if row < 0 or row >= len(self.displayed_stocks):
            return None
        return self.displayed_stocks[row]

    def on_show_hidden_changed(self, state):
        self.show_hidden_stocks = state == Qt.Checked
        self.update_table_display()
        self.fetch_data()

    def update_hide_button_text(self):
        stock = self.get_selected_stock()
        if stock and stock.get('hidden', False):
            self.hide_btn.setText("恢复显示")
        else:
            self.hide_btn.setText("隐藏选中")

    def edit_email_settings(self):
        dialog = EmailSettingsDialog(self.email_config, self)
        if dialog.exec_() == QDialog.Accepted:
            self.email_config = self.normalize_email_config(dialog.get_data())
            self.save_email_config()
            status = "已启用" if self.email_config.get('enabled') else "已停用"
            self.statusBar().showMessage(f"邮件通知{status}")

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
        stock_config = self.get_selected_stock()
        if not stock_config:
            QMessageBox.warning(self, "提示", "请先在列表中选中一只股票！")
            return

        code = stock_config.get('code', '')
        name = stock_config.get('name', '')
        
        dialog = EditAlertDialog(name, code, stock_config, self)
        if dialog.exec_() == QDialog.Accepted:
            stock_config['alerts'] = dialog.get_data()
            self.save_config()
            self.update_table_display()
            self.fetch_data()

    def remove_stock(self):
        stock = self.get_selected_stock()
        if not stock:
            return
        code = stock.get('code', '')
        self.stocks = [s for s in self.stocks if s['code'] != code]
        self.save_config()
        self.update_table_display()
        self.fetch_data()

    def toggle_selected_stock_hidden(self):
        stock = self.get_selected_stock()
        if not stock:
            QMessageBox.warning(self, "提示", "请先在列表中选中一只股票！")
            return

        stock['hidden'] = not stock.get('hidden', False)
        self.save_config()
        self.update_table_display()
        self.fetch_data()
        status = "已隐藏" if stock.get('hidden') else "已恢复显示"
        self.statusBar().showMessage(f"{stock.get('name', stock.get('code', ''))} {status}")

    def update_table_display(self):
        self.displayed_stocks = self.get_visible_stocks()
        self.table.setRowCount(len(self.displayed_stocks))
        
        for i, stock in enumerate(self.displayed_stocks):
            self.table.setItem(i, 0, QTableWidgetItem(stock['code']))
            
            # 使用保存的名字，防止加载出空数据
            name = stock.get('name', '加载中...')
            self.table.setItem(i, 1, QTableWidgetItem(name))
            
            self.table.setItem(i, 2, QTableWidgetItem("--"))
            self.table.setItem(i, 3, QTableWidgetItem("--"))
            
            active_alerts = [alert for alert in stock.get('alerts', []) if alert.get('active', True) and alert.get('target', -1) > 0]
            if not active_alerts:
                self.table.setItem(i, 4, QTableWidgetItem("未设置提醒"))
            else:
                preview = "；".join(alert_to_text(alert) for alert in active_alerts[:2])
                if len(active_alerts) > 2:
                    preview += f"；另 {len(active_alerts) - 2} 条"
                self.table.setItem(i, 4, QTableWidgetItem(preview))
            
            if stock.get('hidden', False):
                status_text = "已隐藏"
            else:
                status_text = f"正在监控（{len(active_alerts)}条提醒）" if active_alerts else "正在监控"
            status_item = QTableWidgetItem(status_text)
            status_item.setForeground(QColor('#6c7086') if stock.get('hidden', False) else QColor('#a6e3a1'))
            self.table.setItem(i, 5, status_item)
            
            # 居中对齐
            for col in range(6):
                item = self.table.item(i, col)
                if item:
                    item.setTextAlignment(Qt.AlignCenter)
        self.update_hide_button_text()

    def fetch_data(self):
        visible_stocks = self.get_visible_stocks()
        if not visible_stocks:
            self.displayed_stocks = []
            self.table.setRowCount(0)
            self.statusBar().showMessage("没有可显示的股票。勾选“显示隐藏股票”可管理隐藏项。")
            return

        market_status = get_market_status()
        if not market_status['is_open']:
            self.show_market_closed_status(market_status)
            self.schedule_next_market_check(market_status['next_open'])
            return

        self.timer.setInterval(self.refresh_rate * 1000)
        self.fetcher = StockFetcher(visible_stocks)
        self.fetcher.data_fetched.connect(self.on_data_fetched)
        self.fetcher.error_occurred.connect(self.on_fetch_error)
        self.fetcher.start()

    def schedule_next_market_check(self, next_open):
        if not next_open:
            self.timer.setInterval(self.refresh_rate * 1000)
            return
        seconds = max(1, int((next_open - datetime.datetime.now()).total_seconds()))
        seconds = min(seconds, 3600)
        self.timer.setInterval(seconds * 1000)

    def show_market_closed_status(self, market_status):
        next_open = market_status.get('next_open')
        next_open_text = next_open.strftime("%m-%d %H:%M") if next_open else "下次开盘"
        status_text = f"{market_status['label']}，暂停行情刷新；预计 {next_open_text} 自动恢复。"
        self.statusBar().showMessage(status_text)

        for row in range(self.table.rowCount()):
            status_item = QTableWidgetItem(f"{market_status['label']}，等待开盘")
            status_item.setForeground(QColor('#f9e2af'))
            status_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 5, status_item)

    def on_fetch_error(self, err):
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.statusBar().showMessage(f"数据获取失败: {err} | 最近更新: {now_str}")

    def on_data_fetched(self, results):
        self.timer.setInterval(self.refresh_rate * 1000)
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.statusBar().showMessage(f"交易中，行情数据已更新 - 最新同步时间: {now_str}")
        
        for row in range(self.table.rowCount()):
            if row >= len(self.displayed_stocks):
                continue
            stock_config = self.displayed_stocks[row]
            code = stock_config.get('code', '')
            
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
                if stock_config:
                    self.check_alert(stock_config, data, row)

    def send_email_alert(self, message, config, data, alert):
        if not self.email_config.get('enabled'):
            return

        alert_type = alert.get('alert_type', 0)
        target = alert.get('target', -1)
        alert_names = ["价格上涨提醒", "价格下跌提醒", "涨幅提醒", "跌幅提醒"]
        alert_name = alert_names[alert_type] if 0 <= alert_type < len(alert_names) else "行情提醒"
        subject_prefix = self.email_config.get('subject_prefix', 'A股行情提醒')
        subject = f"{subject_prefix} - {data['name']} ({config['code']})"
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        body = "\n".join([
            message,
            "",
            f"提醒类型: {alert_name}",
            f"股票代码: {config['code']}",
            f"股票名称: {data['name']}",
            f"当前价格: {data['price']:.2f} 元",
            f"当前涨跌幅: {data['change_percent']:+.2f}%",
            f"触发阈值: {target}",
            f"触发时间: {now_str}",
            "",
            "该股票提醒已自动重置为未设置，避免重复通知。"
        ])

        worker = EmailSender(self.email_config, subject, body, self)
        worker.email_sent.connect(lambda: self.statusBar().showMessage(f"邮件通知已发送: {data['name']} ({config['code']})"))
        worker.email_failed.connect(lambda err: self.statusBar().showMessage(f"邮件通知发送失败: {err}"))
        worker.finished.connect(lambda w=worker: self.cleanup_email_worker(w))
        self.email_workers.append(worker)
        worker.start()

    def cleanup_email_worker(self, worker):
        if worker in self.email_workers:
            self.email_workers.remove(worker)

    def check_alert(self, config, data, row):
        price = data['price']
        change = data['change_percent']
        name = data['name']

        triggered_messages = []
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for alert_config in config.get('alerts', []):
            alert_type = alert_config.get('alert_type', 0)
            target = alert_config.get('target', -1)
            if not alert_config.get('active', True) or target <= 0:
                continue

            triggered = False
            msg = ""

            if alert_type == 0 and price >= target:
                triggered = True
                msg = f"📈 【上涨提醒】 {name} ({config['code']}) 价格已上涨至 {price:.2f} 元，达到目标 {target:.2f} 元！"
            elif alert_type == 1 and price <= target:
                triggered = True
                msg = f"📉 【下跌提醒】 {name} ({config['code']}) 价格已下跌至 {price:.2f} 元，达到目标 {target:.2f} 元！"
            elif alert_type == 2 and change >= target:
                triggered = True
                msg = f"🚀 【暴涨提醒】 {name} ({config['code']}) 涨幅已达 {change:.2f}%，超过设定的 {target:.2f}%！"
            elif alert_type == 3 and change <= -target:
                triggered = True
                msg = f"⚠️ 【暴跌提醒】 {name} ({config['code']}) 跌幅已达 {change:.2f}%，超过设定的 -{target:.2f}%！"

            if not triggered:
                continue

            alert_config['active'] = False
            alert_config['triggered_at'] = now_str
            triggered_messages.append(msg)
            if alert_config.get('email_enabled'):
                self.send_email_alert(msg, config, data, alert_config)

        if triggered_messages:
            status_item = QTableWidgetItem("🔔 已触发提醒")
            status_item.setForeground(QColor('#f9e2af'))
            status_item.setFont(QFont("Segoe UI", 10, QFont.Bold))
            status_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 5, status_item)
            
            self.save_config()

            active_alerts = [alert for alert in config.get('alerts', []) if alert.get('active', True) and alert.get('target', -1) > 0]
            cond_text = "未设置提醒" if not active_alerts else "；".join(alert_to_text(alert) for alert in active_alerts[:2])
            if len(active_alerts) > 2:
                cond_text += f"；另 {len(active_alerts) - 2} 条"
            cond_item = QTableWidgetItem("未设置提醒")
            cond_item.setText(cond_text)
            cond_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 4, cond_item)

            for msg in triggered_messages:
                alert_box = QMessageBox(self)
                alert_box.setWindowFlags(alert_box.windowFlags() | Qt.WindowStaysOnTopHint)
                alert_box.setWindowTitle("行情提醒")
                alert_box.setText(msg)
                alert_box.setIcon(QMessageBox.Information)
                alert_box.setStyleSheet(STYLESHEET)

                # 强制窗口跳到最前面获取焦点
                alert_box.show()
                alert_box.raise_()
                alert_box.activateWindow()
                alert_box.exec_()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLESHEET)
    
    window = StockMonitorApp()
    window.show()
    sys.exit(app.exec_())
