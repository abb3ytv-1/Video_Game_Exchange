from kafka import KafkaConsumer
import json
import os
import smtplib
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Kafka configuration
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "kafka:9092")

# Ethereal Email SMTP configuration
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.ethereal.email")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER)


def send_email(recipients: list, subject: str, body: str):
    """Send an email via Ethereal SMTP."""
    if not SMTP_USER or not SMTP_PASS:
        print("[Warning] SMTP credentials not configured. Email not sent.")
        return False
    
    try:
        # Create message
        msg = MIMEMultipart()
        msg['From'] = SMTP_FROM
        msg['To'] = ', '.join(recipients)
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        
        # Connect to SMTP server and send
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_FROM, recipients, msg.as_string())
        
        print(f"[Email Sent] To: {', '.join(recipients)} | Subject: {subject}")
        return True
    except Exception as e:
        print(f"[Email Error] Failed to send email: {e}")
        return False


def create_consumer():
    """Create Kafka consumer with retry logic."""
    max_retries = 10
    retry_delay = 5
    
    for attempt in range(max_retries):
        try:
            consumer = KafkaConsumer(
                "email_notifications",
                bootstrap_servers=KAFKA_BOOTSTRAP,
                auto_offset_reset='earliest',
                value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                group_id='email-consumer-group'
            )
            print(f"Connected to Kafka at {KAFKA_BOOTSTRAP}")
            return consumer
        except Exception as e:
            print(f"[Attempt {attempt + 1}/{max_retries}] Failed to connect to Kafka: {e}")
            if attempt < max_retries - 1:
                print(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                raise


if __name__ == "__main__":
    print("Email consumer starting...")
    print(f"SMTP Host: {SMTP_HOST}:{SMTP_PORT}")
    print(f"SMTP User: {SMTP_USER}")
    
    consumer = create_consumer()
    print("Listening for email notifications...")
    
    for message in consumer:
        data = message.value
        print(f"\n[Received] Type: {data['type']}")
        print(f"Recipients: {', '.join(data['recipients'])}")
        print(f"Subject: {data['subject']}")
        print(f"Body: {data['body']}")
        
        # Send the actual email
        send_email(
            recipients=data['recipients'],
            subject=data['subject'],
            body=data['body']
        )
        print("-" * 50)
