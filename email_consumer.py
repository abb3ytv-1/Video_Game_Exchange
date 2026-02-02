from kafka import KafkaConsumer
import json
import os

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "kafka:9092")

consumer = KafkaConsumer(
    "email_notifications",
    bootstrap_servers=KAFKA_BOOTSTRAP,
    auto_offset_reset='earliest',
    value_deserializer=lambda m: json.loads(m.decode('utf-8'))
)

print("Email consumer started. Listening for notifications...")

for message in consumer:
    data = message.value
    # Simulate sending email
    print(f"[Email] Type: {data['type']}")
    print(f"Recipients: {', '.join(data['recipients'])}")
    print(f"Subject: {data['subject']}")
    print(f"Body: {data['body']}")
    print("-" * 50)
