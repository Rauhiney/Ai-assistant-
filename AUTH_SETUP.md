# DENZ Secure OTP Setup

DENZ now uses password plus OTP for login. Registration is also OTP-verified:

1. The user enters an email or phone number.
2. DENZ sends an OTP to that email or phone.
3. The user enters the OTP.
4. Only then does the user create a username and password.
5. The account is created after successful OTP verification.

In secure mode, OTP codes are never returned to the browser; they must be delivered by email or SMS.

## Gmail OTP

Use a Gmail app password, not your normal Gmail password.

Set these environment variables:

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=yourgmail@gmail.com
SMTP_PASSWORD=your_16_character_gmail_app_password
SMTP_FROM=yourgmail@gmail.com
OTP_RETURN_CODE=false
```

## Phone OTP

Phone OTP uses Twilio SMS. Phone numbers must be in E.164 format, for example `+919876543210`.

Set these environment variables:

```env
SMS_PROVIDER=twilio
TWILIO_ACCOUNT_SID=your_twilio_account_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_FROM_NUMBER=+1234567890
OTP_RETURN_CODE=false
```

## Admin OTP

The admin account also needs an OTP destination:

```env
ADMIN_USERNAME=admin
ADMIN_PASSWORD=use_a_strong_password
ADMIN_EMAIL=yourgmail@gmail.com
ADMIN_PHONE=+919876543210
```

## Local Development Only

If you do not have Gmail/Twilio configured yet, you can temporarily set:

```env
OTP_RETURN_CODE=true
```

This returns the OTP in the API response for local testing. Do not use it in production.
