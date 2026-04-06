import sys
import pika
from json import dumps, loads
from utils.detect_mines import find_mine_pins_using_threads


DEMINE_QUEUE = "Demine-Queue"
DEFUSED_QUEUE = "Defused-Mines"


def compute_pin(mine_info: dict) -> str:
    find_mine_pins_using_threads(mine_info)
    return mine_info["mine_pin_code"]


def publish_result(channel, message: dict):
    channel.basic_publish(
        exchange="",
        routing_key=DEFUSED_QUEUE,
        body=dumps(message)
    )


def process_task(body, deminer_id, channel):
    task = loads(body.decode())

    rover_id = task["rover_id"]
    row = task["row_coordinate"]
    col = task["col_coordinate"]
    serial = task["mine_serial_number"]

    print(f"[Deminer {deminer_id}] Processing mine at ({row}, {col}) | Serial: {serial}")

    mine_info = {
        "mine_location": [row, col],
        "mine_serial_number": serial
    }

    pin_code = compute_pin(mine_info)

    print(f"[Deminer {deminer_id}] PIN computed: {pin_code}")

    result = {
        "rover_id": rover_id,
        "deminer_id": deminer_id,
        "row_coordinate": row,
        "col_coordinate": col,
        "mine_serial_number": serial,
        "deactivation_pin_code": pin_code
    }

    publish_result(channel, result)

    print(f"[Deminer {deminer_id}] Result published successfully")


def setup_channel():
    connection = pika.BlockingConnection(pika.ConnectionParameters(host="localhost"))
    channel = connection.channel()

    channel.queue_declare(queue=DEMINE_QUEUE)
    channel.queue_declare(queue=DEFUSED_QUEUE)

    return connection, channel


def main():
    deminer_id = sys.argv[1]
    connection, channel = setup_channel()

    def callback(ch, method, properties, body):
        process_task(body, deminer_id, channel)
        ch.basic_ack(delivery_tag=method.delivery_tag)

    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=DEMINE_QUEUE, on_message_callback=callback)

    print(f"[Deminer {deminer_id}] Waiting for tasks...")

    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        print("Deminer shutting down...")
        channel.stop_consuming()
    finally:
        connection.close()


if __name__ == "__main__":
    main()