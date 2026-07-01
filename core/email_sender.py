"""Envio de e-mail via Gmail SMTP."""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage


def enviar_email(assunto, html, cfg, imagens=None):
    """Envia e-mail HTML. `imagens` é um dict opcional {cid: bytes_png} para inline."""
    if imagens:
        msg = MIMEMultipart("related")
        alt = MIMEMultipart("alternative")
        alt.attach(MIMEText(html, "html", "utf-8"))
        msg.attach(alt)
        for cid, dados in imagens.items():
            img = MIMEImage(dados, _subtype="png")
            img.add_header("Content-ID", f"<{cid}>")
            img.add_header("Content-Disposition", "inline")
            msg.attach(img)
    else:
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(html, "html", "utf-8"))

    msg["Subject"] = assunto
    msg["From"] = cfg.gmail_user
    msg["To"] = cfg.email_to

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(cfg.gmail_user, cfg.gmail_app_password)
        server.sendmail(cfg.gmail_user, cfg.email_to.split(","), msg.as_string())
