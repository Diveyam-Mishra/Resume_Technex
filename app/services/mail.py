import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, List, Optional, Union
from urllib.parse import urlparse

from app.config.settings import settings

logger = logging.getLogger(__name__)


def send_email(
    to: Union[str, List[str]],
    subject: str,
    text: str,
    html: Optional[str] = None,
    cc: Optional[List[str]] = None,
    bcc: Optional[List[str]] = None,
    reply_to: Optional[str] = None,
    attachments: Optional[Dict[str, bytes]] = None
) -> None:
    """
    Send an email using the configured SMTP server.
    If SMTP_URL is not set, logs the email to console instead.
    """
    # If SMTP_URL is not set, log the email to console
    if not settings.SMTP_URL:
        logger.info(f"SMTP not configured. Would have sent email: To={to}, Subject={subject}, Body={text[:100]}...")
        return
    
    # Parse SMTP URL
    parsed_url = urlparse(str(settings.SMTP_URL))
    
    # Determine if we're using SSL
    is_ssl = parsed_url.scheme == "smtps"
    
    # Get host and port
    host = parsed_url.hostname or "localhost"
    port = parsed_url.port or (465 if is_ssl else 25)
    
    # Get username and password if provided
    username = parsed_url.username
    password = parsed_url.password
    
    # Create message
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = settings.MAIL_FROM
    
    # Handle recipients
    if isinstance(to, list):
        msg['To'] = ', '.join(to)
    else:
        msg['To'] = to
    
    if cc:
        msg['Cc'] = ', '.join(cc)
    
    if reply_to:
        msg['Reply-To'] = reply_to
    
    # Add text part
    msg.attach(MIMEText(text, 'plain'))
    
    # Add HTML part if provided
    if html:
        msg.attach(MIMEText(html, 'html'))
    
    # Determine all recipients
    recipients = [to] if isinstance(to, str) else to
    if cc:
        recipients.extend(cc)
    if bcc:
        recipients.extend(bcc)
    
    try:
        # Create SMTP connection based on SSL or not
        if is_ssl:
            server = smtplib.SMTP_SSL(host, port)
        else:
            server = smtplib.SMTP(host, port)
            server.ehlo()
            if server.has_extn('STARTTLS'):
                server.starttls()
                server.ehlo()
        
        # Login if credentials are provided
        if username and password:
            server.login(username, password)
        
        # Send the email
        server.sendmail(settings.MAIL_FROM, recipients, msg.as_string())
        server.quit()
        
        logger.info(f"Email sent successfully to {to}")
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        # Don't raise the exception, just log it
        # This is to prevent email sending failures from affecting the application