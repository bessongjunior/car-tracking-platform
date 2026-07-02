"""
Gmail SMTP email sender.

Uses Python's built-in smtplib with STARTTLS on port 587.
Sending is dispatched to a daemon thread so it never blocks a request.

Requirements in Google Account:
  1. Enable 2-Step Verification
  2. Google Account → Security → App passwords
  3. Select "Mail" + "Other (CarTracker)" → copy the 16-char password
  4. Set GMAIL_SENDER and GMAIL_APP_PASSWORD in backend/.env
"""
import logging
import smtplib
import threading
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

log = logging.getLogger(__name__)


# ── HTML template ─────────────────────────────────────────────────────────────

def _otp_html(otp: str, user_name: str, expiry_minutes: int) -> str:
    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Your CarTracker OTP</title>
</head>
<body style="margin:0;padding:0;background:#F4F6F9;font-family:'Segoe UI',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0">
    <tr>
      <td align="center" style="padding:40px 16px;">
        <table width="520" cellpadding="0" cellspacing="0"
               style="background:#ffffff;border-radius:12px;
                      box-shadow:0 4px 24px rgba(0,0,0,0.08);overflow:hidden;">

          <!-- Header -->
          <tr>
            <td style="background:#1565C0;padding:32px 40px;text-align:center;">
              <span style="font-size:22px;font-weight:700;color:#ffffff;
                           letter-spacing:3px;text-transform:uppercase;">
                &#128663; CarTracker
              </span>
              <p style="margin:6px 0 0;color:#90CAF9;font-size:13px;letter-spacing:1px;">
                Precise Fleet Intelligence
              </p>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding:40px 40px 32px;">
              <p style="margin:0 0 8px;font-size:16px;color:#212121;font-weight:600;">
                Hello{', ' + user_name if user_name else ''},
              </p>
              <p style="margin:0 0 28px;font-size:14px;color:#616161;line-height:1.6;">
                A sign-in request was made for your CarTracker account.
                Use the verification code below to complete your login.
              </p>

              <!-- OTP box -->
              <div style="background:#F0F4FF;border:2px dashed #1565C0;
                          border-radius:10px;padding:28px 0;text-align:center;
                          margin-bottom:28px;">
                <p style="margin:0 0 4px;font-size:11px;color:#1565C0;
                           font-weight:700;letter-spacing:2px;text-transform:uppercase;">
                  Verification Code
                </p>
                <p style="margin:0;font-size:42px;font-weight:800;
                           letter-spacing:12px;color:#1565C0;">
                  {otp}
                </p>
              </div>

              <p style="margin:0 0 24px;font-size:13px;color:#9E9E9E;text-align:center;">
                This code expires in <strong style="color:#E53935;">{expiry_minutes} minutes</strong>.
                Do not share it with anyone.
              </p>

              <hr style="border:none;border-top:1px solid #EEEEEE;margin:0 0 24px;"/>

              <p style="margin:0;font-size:12px;color:#BDBDBD;line-height:1.6;">
                If you did not request this code, your account credentials may be
                compromised. Please contact your fleet administrator immediately.<br/><br/>
                &mdash; The CarTracker Security Team &bull; Tief Technologies Ltd
              </p>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background:#FAFAFA;padding:18px 40px;text-align:center;
                       border-top:1px solid #EEEEEE;">
              <p style="margin:0;font-size:11px;color:#BDBDBD;">
                &copy; 2025 Tief Technologies Ltd &bull; CarTracker Fleet Platform
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""


# ── Core sender ───────────────────────────────────────────────────────────────

def _send(to_email: str, subject: str, html: str,
          sender: str, app_password: str,
          smtp_host: str, smtp_port: int) -> None:
    """Runs inside a daemon thread."""
    if not app_password:
        log.warning('GMAIL_APP_PASSWORD not set — skipping email to %s', to_email)
        return
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From']    = f'CarTracker <{sender}>'
        msg['To']      = to_email
        msg.attach(MIMEText(html, 'html', 'utf-8'))

        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(sender, app_password)
            smtp.sendmail(sender, to_email, msg.as_string())

        log.info('OTP email delivered → %s', to_email)
    except smtplib.SMTPAuthenticationError:
        log.error(
            'Gmail authentication failed for %s. '
            'Make sure you are using a Google App Password, not your account password.',
            sender,
        )
    except Exception as exc:
        log.error('Email send failed to %s: %s', to_email, exc)


def send_otp_email(
    to_email: str,
    otp: str,
    user_name: str = '',
    *,
    sender: str,
    app_password: str,
    smtp_host: str = 'smtp.gmail.com',
    smtp_port: int = 587,
    expiry_minutes: int = 5,
) -> None:
    """
    Send the OTP verification email in a background daemon thread.
    Returns immediately; any send failure is logged but never raises.
    """
    html = _otp_html(otp, user_name, expiry_minutes)
    subject = f'{otp} is your CarTracker verification code'
    thread = threading.Thread(
        target=_send,
        args=(to_email, subject, html, sender, app_password, smtp_host, smtp_port),
        daemon=True,
    )
    thread.start()
