async def send_email(emails: List[str]):
    html = """<p>Hi, Thanks for registering</p>"""

    message = MessageSchema(
        subject = "Registration Confirmation",
        recipients = emails,
        body = html,
        subtype = MessageType.html
    )

    fm = FastMail(conf)
    await fm.send_message(message)
    print ({"status": "Email Sent"})