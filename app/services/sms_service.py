"""
WAY2WEAR — OTP SMS SERVICE
Supports Fast2SMS, MSG91, Twilio.
Set SMS_PROVIDER in .env to switch between them.
"""
import httpx
import logging
from app.config import settings

logger = logging.getLogger("way2wear")


# ══════════════════════════════════════════════
# FAST2SMS  (cheapest for India — ₹0.10/SMS)
# Sign up: https://www.fast2sms.com
# Free trial: ₹50 credit on signup
# ══════════════════════════════════════════════
async def send_via_fast2sms(phone: str, otp: str) -> bool:
    """
    phone: must be 10-digit Indian number (without +91)
    Fast2SMS doesn't need +91 prefix
    """
    api_key = getattr(settings, "FAST2SMS_API_KEY", None)
    if not api_key:
        return False

    # Strip +91 if present
    number = phone.replace("+91", "").replace("+", "").strip()

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                "https://www.fast2sms.com/dev/bulkV2",
                headers={
                    "authorization": api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "route": "otp",           # OTP route
                    "variables_values": otp,   # The OTP value
                    "numbers": number,         # 10-digit number
                    "flash": 0,
                },
            )
            data = response.json()
            if data.get("return") is True:
                logger.info(f"Fast2SMS OTP sent to {number}")
                return True
            else:
                logger.error(f"Fast2SMS error: {data}")
                return False
    except Exception as e:
        logger.error(f"Fast2SMS exception: {e}")
        return False


# ══════════════════════════════════════════════
# MSG91  (most popular in India — ₹0.18/SMS)
# Sign up: https://msg91.com
# Free trial: 100 free SMS
# ══════════════════════════════════════════════
async def send_via_msg91(phone: str, otp: str) -> bool:
    """
    Requires a template to be created in MSG91 dashboard.
    Template: "Your Way2Wear OTP is ##OTP##. Valid for 5 minutes."
    """
    auth_key  = getattr(settings, "MSG91_AUTH_KEY", None)
    sender_id = getattr(settings, "MSG91_SENDER_ID", "W2WEAR")
    template_id = getattr(settings, "MSG91_TEMPLATE_ID", None)

    if not auth_key:
        return False

    # MSG91 needs number with country code (no +)
    number = phone.replace("+", "").strip()
    if not number.startswith("91"):
        number = "91" + number

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                "https://control.msg91.com/api/v5/otp",
                headers={
                    "authkey": auth_key,
                    "Content-Type": "application/json",
                },
                json={
                    "template_id": template_id,
                    "mobile":      number,
                    "authkey":     auth_key,
                    "otp":         otp,
                    "sender":      sender_id,
                },
            )
            data = response.json()
            if data.get("type") == "success":
                logger.info(f"MSG91 OTP sent to {number}")
                return True
            else:
                logger.error(f"MSG91 error: {data}")
                return False
    except Exception as e:
        logger.error(f"MSG91 exception: {e}")
        return False


# ══════════════════════════════════════════════
# TWILIO  (international — ₹6/SMS)
# Sign up: https://twilio.com
# Free trial: $15 credit
# ══════════════════════════════════════════════
async def send_via_twilio(phone: str, otp: str) -> bool:
    twilio_sid   = getattr(settings, "TWILIO_ACCOUNT_SID", None)
    twilio_token = getattr(settings, "TWILIO_AUTH_TOKEN", None)
    twilio_from  = getattr(settings, "TWILIO_FROM_NUMBER", None)

    if not all([twilio_sid, twilio_token, twilio_from]):
        return False

    try:
        import base64
        credentials = base64.b64encode(
            f"{twilio_sid}:{twilio_token}".encode()
        ).decode()

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{twilio_sid}/Messages.json",
                headers={
                    "Authorization": f"Basic {credentials}",
                    "Content-Type":  "application/x-www-form-urlencoded",
                },
                data={
                    "From": twilio_from,
                    "To":   phone,
                    "Body": f"Your Way2Wear OTP is {otp}. Valid for 5 minutes. Do not share.",
                },
            )
            data = response.json()
            if response.status_code == 201:
                logger.info(f"Twilio OTP sent to {phone}")
                return True
            else:
                logger.error(f"Twilio error: {data}")
                return False
    except Exception as e:
        logger.error(f"Twilio exception: {e}")
        return False


# ══════════════════════════════════════════════
# MAIN SEND FUNCTION — auto-selects provider
# ══════════════════════════════════════════════
async def send_otp_sms(phone: str, otp: str) -> tuple[bool, str]:
    """
    Returns (success: bool, dev_otp: str | None)
    dev_otp is only returned when no provider is configured (dev mode)
    """
    provider = getattr(settings, "SMS_PROVIDER", "").lower().strip()

    # ── Fast2SMS ──────────────────────────────
    if provider == "fast2sms":
        success = await send_via_fast2sms(phone, otp)
        return success, None

    # ── MSG91 ─────────────────────────────────
    if provider == "msg91":
        success = await send_via_msg91(phone, otp)
        return success, None

    # ── Twilio ────────────────────────────────
    if provider == "twilio":
        success = await send_via_twilio(phone, otp)
        return success, None

    # ── Dev mode (no provider configured) ─────
    logger.warning(f"\n{'='*45}")
    logger.warning(f"  📱 DEV OTP for {phone}: {otp}")
    logger.warning(f"{'='*45}\n")
    return True, otp  # return OTP to show in UI during development
