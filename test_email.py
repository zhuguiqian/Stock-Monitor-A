import datetime
import json
import os
import smtplib
import ssl
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid
from pathlib import Path

EMAIL_CONFIG_FILE = "email_config.json"


def parse_recipients(value):
    if isinstance(value, list):
        return [item.strip() for item in value if item and item.strip()]
    return [item.strip() for item in str(value).replace(";", ",").split(",") if item.strip()]


def get_password(config):
    password_env = config.get("password_env", "").strip()
    if password_env:
        return os.environ.get(password_env) or config.get("password", "")
    return config.get("password", "")


def main():
    config_path = Path(EMAIL_CONFIG_FILE)
    if not config_path.exists():
        raise SystemExit(f"找不到 {EMAIL_CONFIG_FILE}，请先在程序里保存邮件设置。")

    config = json.loads(config_path.read_text(encoding="utf-8"))
    recipients = parse_recipients(config.get("recipients", ""))
    smtp_server = config.get("smtp_server", "").strip()
    smtp_port = int(config.get("smtp_port", 465))
    sender = config.get("sender", "").strip()
    password = get_password(config)
    security = config.get("security", "ssl")

    if not config.get("enabled"):
        raise SystemExit("邮件通知未启用。")
    if not smtp_server or not sender or not password or not recipients:
        raise SystemExit("邮件配置不完整。")

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    subject = f"A股行情提醒 - 中文编码测试 {now}"
    body = "\n".join([
        "这是一封 Stock Monitor A 的中文编码测试邮件。",
        "股票名称: 广电运通",
        "提醒内容: 价格提醒，涨跌幅提醒。",
        f"发送时间: {now}",
        "如果这几行中文正常显示，说明邮件编码问题已经修复。"
    ])

    message = MIMEText(body, "plain", "utf-8")
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message["Subject"] = Header(subject, "utf-8").encode()
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid(domain=sender.split("@")[-1] if "@" in sender else None)

    context = ssl.create_default_context()
    if security == "ssl":
        with smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=30, context=context) as server:
            server.login(sender, password)
            refused = server.sendmail(sender, recipients, message.as_string())
    else:
        with smtplib.SMTP(smtp_server, smtp_port, timeout=30) as server:
            server.ehlo()
            if security == "starttls":
                server.starttls(context=context)
                server.ehlo()
            server.login(sender, password)
            refused = server.sendmail(sender, recipients, message.as_string())

    print("TEST_EMAIL_SENT")
    print("time:", now)
    print("smtp:", smtp_server, smtp_port)
    print("recipient_count:", len(recipients))
    print("refused_count:", len(refused))


if __name__ == "__main__":
    main()
