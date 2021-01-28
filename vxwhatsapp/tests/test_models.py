from vxwhatsapp.models import Event, Message


def test_message_serialisation():
    """
    Message should be able to be serialised and deserialised with no changes
    """
    message = Message(
        to_addr="27820001001",
        from_addr="27820001002",
        transport_name="whatsapp",
        transport_type=Message.TRANSPORT_TYPE.WHATSAPP,
        in_reply_to="original-message-id",
        session_event=Message.SESSION_EVENT.NEW,
        content="message content",
        to_addr_type=Message.ADDRESS_TYPE.MSISDN,
        from_addr_type=Message.ADDRESS_TYPE.MSISDN,
    )
    assert message == Message.from_json(message.to_json())


def test_event_serialization():
    """
    Event should be able to be serialised and deserialised with no changes
    """
    event = Event(
        user_message_id="message-id",
        event_type=Event.EVENT_TYPE.DELIVERY_REPORT,
        delivery_status=Event.DELIVERY_STATUS.DELIVERED,
    )
    assert event == Event.from_json(event.to_json())


def test_event_ack():
    """
    sent_message_id should be required for an ack
    """
    exception = None
    try:
        Event(user_message_id="message-id", event_type=Event.EVENT_TYPE.ACK)
    except AssertionError as e:
        exception = e
    assert exception is not None

    Event(
        user_message_id="message-id",
        event_type=Event.EVENT_TYPE.ACK,
        sent_message_id="message-id",
    )


def test_event_nack():
    """
    nack_reason should be required for a nack
    """
    exception = None
    try:
        Event(user_message_id="message-id", event_type=Event.EVENT_TYPE.NACK)
    except AssertionError as e:
        exception = e
    assert exception is not None

    Event(
        user_message_id="message-id",
        event_type=Event.EVENT_TYPE.NACK,
        nack_reason="cannot reach service",
    )


def test_event_delivery_report():
    """
    delivery_status should be required for a delivery report
    """
    exception = None
    try:
        Event(user_message_id="message-id", event_type=Event.EVENT_TYPE.DELIVERY_REPORT)
    except AssertionError as e:
        exception = e
    assert exception is not None

    Event(
        user_message_id="message-id",
        event_type=Event.EVENT_TYPE.DELIVERY_REPORT,
        delivery_status=Event.DELIVERY_STATUS.DELIVERED,
    )
