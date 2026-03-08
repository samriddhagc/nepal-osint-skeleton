"""Send OTP emails via Resend."""
import logging

import resend

from app.config import get_settings

logger = logging.getLogger(__name__)


def send_otp_email(to_email: str, otp_code: str) -> bool:
    """Send a 6-digit OTP to the given email address.

    Returns True if email was actually sent, False if in dev mode (no API key).
    """
    settings = get_settings()

    if not settings.resend_api_key:
        logger.warning("RESEND_API_KEY not set — OTP email not sent (dev mode)")
        logger.info("OTP for %s: %s", to_email, otp_code)
        return False

    resend.api_key = settings.resend_api_key

    html = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 480px; margin: 0 auto; background: #111418; border-radius: 12px; padding: 32px; color: #f0f0f0;">
      <h2 style="margin: 0 0 8px; font-size: 22px; color: #ffffff;">Nepal OSINT</h2>
      <p style="margin: 0 0 24px; font-size: 14px; color: #999;">Nepal OSINT Platform</p>
      <p style="font-size: 15px; color: #ddd; margin-bottom: 24px;">Enter this code to verify your email and create your account:</p>
      <div style="background: #1c2127; border: 1px solid #333; border-radius: 8px; padding: 20px; text-align: center; margin-bottom: 24px;">
        <span style="font-family: 'SF Mono', Monaco, Consolas, monospace; font-size: 32px; letter-spacing: 8px; color: #ffffff; font-weight: 700;">{otp_code}</span>
      </div>
      <p style="font-size: 13px; color: #888; margin-bottom: 4px;">This code expires in 10 minutes.</p>
      <p style="font-size: 13px; color: #888; margin: 0;">If you didn't request this, ignore this email.</p>
    </div>
    """

    resend.Emails.send({
        "from": settings.resend_from_email,
        "to": [to_email],
        "subject": "Nepal OSINT — Your verification code",
        "html": html,
    })
    return True
