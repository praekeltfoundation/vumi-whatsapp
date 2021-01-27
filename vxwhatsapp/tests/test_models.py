from vxwhatsapp.models import Message


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
