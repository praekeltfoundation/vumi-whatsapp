from jsonschema import validate
from jsonschema.validators import validator_for

from vxwhatsapp.schema import whatsapp_webhook_schema

# Examples from the whatsapp docs
# https://developers.facebook.com/docs/whatsapp/api/webhooks/inbound
# https://developers.facebook.com/docs/whatsapp/api/webhooks/outbound
# https://developers.facebook.com/docs/whatsapp/api/webhooks
whatsapp_valid = [
    {
        "contacts": [{"profile": {"name": "Kerry Fisher"}, "wa_id": "16315551234"}],
        "messages": [
            {
                "from": "16315551234",
                "id": "ABGGFlA5FpafAgo6tHcNmNjXmuSf",
                "timestamp": "1518694235",
                "text": {"body": "Hello this is an answer"},
                "type": "text",
            }
        ],
    },
    {
        "contacts": [{"profile": {"name": "Kerry Fisher"}, "wa_id": "16315551234"}],
        "messages": [
            {
                "from": "16315551234",
                "id": "ABGGFlA5FpafAgo6tHcNmNjXmuSf",
                "location": {
                    "address": "Main Street Beach, Santa Cruz, CA",
                    "latitude": 38.9806263495,
                    "longitude": -131.9428612257,
                    "name": "Main Street Beach",
                    "url": "https://foursquare.com/v/4d7031d35b5df7744",
                },
                "timestamp": "1521497875",
                "type": "location",
            }
        ],
    },
    {
        "contacts": [{"profile": {"name": "Kerry Fisher"}, "wa_id": "16315551234"}],
        "messages": [
            {
                "contacts": [
                    {
                        "addresses": [
                            {
                                "city": "Menlo Park",
                                "country": "United States",
                                "country_code": "us",
                                "state": "CA",
                                "street": "1 Hacker Way",
                                "type": "WORK",
                                "zip": "94025",
                            }
                        ],
                        "birthday": "2012-08-18",
                        "contact_image": "/9j/4AAQSkZJRgABAQEAZABkAAD/2wBDAAgGBgcGB...",
                        "emails": [{"email": "kfish@fb.com", "type": "WORK"}],
                        "ims": [{"service": "AIM", "user_id": "kfish"}],
                        "name": {
                            "first_name": "Kerry",
                            "formatted_name": "Kerry Fisher",
                            "last_name": "Fisher",
                        },
                        "org": {"company": "Facebook"},
                        "phones": [
                            {"phone": "+1 (940) 555-1234", "type": "CELL"},
                            {
                                "phone": "+1 (650) 555-1234",
                                "type": "WORK",
                                "wa_id": "16505551234",
                            },
                        ],
                        "urls": [{"url": "https://www.facebook.com", "type": "WORK"}],
                    }
                ],
                "from": "16505551234",
                "id": "ABGGFlA4dSRvAgo6C4Z53hMh1ugR",
                "timestamp": "1537248012",
                "type": "contacts",
            }
        ],
    },
    {
        "contacts": [{"profile": {"name": "Kerry Fisher"}, "wa_id": "16315551234"}],
        "messages": [
            {
                "context": {"forwarded": True},
                "from": "16315558011",
                "id": "ABGGFmkiWVVPAgo-sOGh7pv13wVJ",
                "text": {"body": "Party at Dotty's tonight!"},
                "timestamp": "1593068329",
                "type": "text",
            }
        ],
    },
    {
        "contacts": [{"profile": {"name": "Kerry Fisher"}, "wa_id": "16315551234"}],
        "messages": [
            {
                "context": {"frequently_forwarded": True},
                "from": "16315558011",
                "id": "ABGGFmkiWVVPAgo-sBTHfS3swNIl",
                "timestamp": "1593068225",
                "type": "video",
                "video": {
                    "id": "e144be57-12b1-4035-a520-703fcc87ef45",
                    "mime_type": "video/mp4",
                    "sha256": "02c4e68a4f0d6af5ec6ef02120e20d15f520a4dd473b535abec1aab1"
                    "75c4e8b9",
                },
            }
        ],
    },
    {
        "contacts": [{"profile": {"name": "Kerry Fisher"}, "wa_id": "16315551234"}],
        "messages": [
            {
                "errors": [
                    {
                        "code": 501,
                        "details": "Message type is not currently supported",
                        "title": "Unknown message type",
                    }
                ],
                "from": "16315551234",
                "id": "ABGGFRBzFymPAgo6N9KKs7HsN6eB",
                "timestamp": "1531933468",
                "type": "unknown",
            }
        ],
    },
    {
        "contacts": [{"profile": {"name": "Kerry Fisher"}, "wa_id": "16315551234"}],
        "messages": [
            {
                "from": "16315553601",
                "id": "ABGGFjFVU2AfAgo6V-Hc5eCgK5Gh",
                "identity": {
                    "acknowledged": True,
                    "created_timestamp": 1602532300000,
                    "hash": "Sjvjlx8G6Z0=",
                },
                "text": {"body": "Hi from new number 3601"},
                "timestamp": "1602532300",
                "type": "text",
            }
        ],
    },
    {
        "contacts": [{"profile": {"name": "Kerry Fisher"}, "wa_id": "16505551234"}],
        "messages": [
            {
                "button": {"payload": "No-Button-Payload", "text": "No"},
                "context": {"from": "16315558007", "id": "gBGGFmkiWVVPAgkgQkwi7IORac0"},
                "from": "16505551234",
                "id": "ABGGFmkiWVVPAgo-sKD87hgxPHdF",
                "timestamp": "1591210827",
                "type": "button",
            }
        ],
    },
    {
        "messages": [
            {
                "from": "16315551234",
                "id": "ABGGFlA5FpafAgo6tHcNmNjXmuSf",
                "image": {
                    "file": "/usr/local/wamedia/shared/b1cf38-8734-4ad3-b4a1-ef0c10d0d6"
                    "83",
                    "id": "b1c68f38-8734-4ad3-b4a1-ef0c10d683",
                    "mime_type": "image/jpeg",
                    "sha256": "29ed500fa64eb55fc19dc4124acb300e5dcc54a0f822a301ae99944d"
                    "b",
                    "caption": "Check out my new phone!",
                },
                "timestamp": "1521497954",
                "type": "image",
            }
        ]
    },
    {
        "messages": [
            {
                "from": "16315551234",
                "id": "ABGGFlA5FpafAgo6tHcNmNjXmuSf",
                "timestamp": "1522189546",
                "type": "document",
                "document": {
                    "caption": "80skaraokesonglistartist",
                    "file": "/usr/local/wamedia/shared/fc233119-733f-49c-bcbd-b2f68f798"
                    "e33",
                    "id": "fc233119-733f-49c-bcbd-b2f68f798e33",
                    "mime_type": "application/pdf",
                    "sha256": "3b11fa6ef2bde1dd14726e09d3edaf782120919d06f6484f32d5d5ca"
                    "a4b8e",
                },
            }
        ]
    },
    {
        "messages": [
            {
                "from": "16315551234",
                "id": "ABGGFlA5FpafAgo6tHcNmNjXmuSf",
                "timestamp": "1521827831",
                "type": "voice",
                "voice": {
                    "file": "/usr/local/wamedia/shared/463e/b7ec/ff4e4d9bb1101879cbd411"
                    "b2",
                    "id": "463eb7ec-ff4e-4d9b-b110-1879cbd411b2",
                    "mime_type": "audio/ogg; codecs=opus",
                    "sha256": "fa9e1807d936b7cebe63654ea3a7912b1fa9479220258d823590521e"
                    "f53b0710",
                },
            }
        ]
    },
    {
        "messages": [
            {
                "from": "16315551234",
                "id": "ABGGFlA5FpafAgo6tHcNmNjXmuSf",
                "timestamp": "1521827831",
                "type": "sticker",
                "sticker": {
                    "id": "b1c68f38-8734-4ad3-b4a1-ef0c10d683",
                    "metadata": {
                        "sticker-pack-id": "463eb7ec-ff4e-4d9b-b110-1879cbd411b2",
                        "sticker-pack-name": "Happy New Year",
                        "sticker-pack-publisher": "Kerry Fisher",
                        "emojis": ["🐥", "😃"],
                        "ios-app-store-link": "https://apps.apple.com/app/id3133333",
                        "android-app-store-link": "https://play.google.com/store/apps/d"
                        "etails?id=com.example",
                        "is-first-party-sticker": 0,  # integer
                    },
                    "mime_type": "image/webp",
                    "sha256": "fa9e1807d936b7cebe63654ea3a7912b1fa9479220258d823590521e"
                    "f53b0710",
                },
            }
        ]
    },
    {
        "contacts": [{"profile": {"name": "Kerry Fisher"}, "wa_id": "16315551234"}],
        "messages": [
            {
                "context": {
                    "from": "16315558011",
                    "id": "ABGGFlA5FpafAgo6tHcNmNjXmuSf",
                },
                "from": "16315551234",
                "id": "gBGGFlA5FpafAgkOuJbRq54qwbM",
                "text": {"body": "Yes, count me in!"},
                "timestamp": "1521499915",
                "type": "text",
            }
        ],
    },
    {
        "messages": [
            {
                "from": "16315558889",
                "id": "ABGGFjFVWIifAzNzeXMtMTYzMTU1NTg4ODlAcy53aGF0c2FwcC5uZXQtMTU3NDA4"
                "MDEwMjIxMy1jaGFuZ2U",
                "system": {
                    "body": "‎User A changed from +1 (631) 555-8889 to +1 (631) 555-889"
                    "0‎",
                    "new_wa_id": "16315558890",
                    "type": "user_changed_number",
                },
                "timestamp": "1574080102",
                "type": "system",
            }
        ]
    },
    {
        "messages": [
            {
                "from": "16315553601",
                "id": "ABGGFjFVU2AfAzVzeXMtMTYzMTU1NTM2MDFAcy53aGF0c2FwcC5uZXQtMTYwMjUz"
                "NTM1NjMzMi1pZGVudGl0eQ",
                "system": {
                    "identity": "Rc/eg9Rl0JA=",
                    "type": "user_identity_changed",
                    "user": "16315553601",
                },
                "timestamp": "1602535356",
                "type": "system",
            }
        ]
    },
    {
        "messages": [
            {
                "context": {
                    "from": "16315555544",
                    "id": "gBGGFlA5FpafAgkOuJbRq54qwbM",
                    "mentions": ["16315551000", "16315551099"],
                },
                "from": "16315551234 ",
                "id": "ABGGFlA5FpafAgo6tHcNmNjXmuSf",
                "timestamp": "1504902988",
                "text": {"body": "@16315551000 and @16315551099 are mentioned"},
                "type": "text",
            }
        ]
    },
    {
        "statuses": [
            {
                "conversation": {"id": "5fc5524522b4c9bc0e2018ad810a095a"},
                "id": "gBGGEgFVUXl_AgkUBIUqicVXyZY",
                "pricing": {"billable": True, "pricing_model": "CBP"},
                "recipient_id": "12015551797",
                "status": "sent",
                "timestamp": "1609879800",
            }
        ]
    },
    {
        "statuses": [
            {
                "id": "3A0C810BBE72C289F9CD",
                "recipient_id": "19075550014",
                "status": "sent",
                "timestamp": "1603408535",
                "conversation": {"id": "532b57b5f6e63595ccd74c6010e5c5c7"},
                "pricing": {"pricing_model": "CBP", "billable": False},
            }
        ]
    },
    {
        "statuses": [
            {
                "id": "ABGGFlA5FpafAgo6tHcNmNjXmuSf",
                "recipient_id": "16315555555",
                "status": "delivered",
                "timestamp": "1518694708",
            }
        ]
    },
    {
        "statuses": [
            {
                "conversation": {"id": "b67b498c788be212a30515d377620739"},
                "id": "gBGGEgFVUXl_AgmQ1p4lCm7vdfo",
                "pricing": {"billable": True, "pricing_model": "CBP"},
                "recipient_id": "12015551797",
                "status": "delivered",
                "timestamp": "1610413994",
            }
        ]
    },
    {
        "statuses": [
            {
                "id": "3A0C810BBE72C289F9CD",
                "recipient_id": "19075550014",
                "status": "delivered",
                "timestamp": "1603408535",
                "conversation": {"id": "532b57b5f6e63595ccd74c6010e5c5c7"},
                "pricing": {"pricing_model": "CBP", "billable": False},
            }
        ]
    },
    {
        "statuses": [
            {
                "id": "ABGGFlA5FpafAgo6tHcNmNjXmuSf",
                "recipient_id": "16315555555",
                "status": "read",
                "timestamp": "1518694722",
            }
        ]
    },
    {
        "statuses": [
            {
                "conversation": {"id": "e118e912f7b8212088f2ccad1d8f70bf"},
                "id": "gBGGFlB5YjhvAgnhuF1qIUvCo7A",
                "pricing": {"billable": True, "pricing_model": "CBP"},
                "recipient_id": "16315555555",
                "status": "read",
                "timestamp": "1610561171",
            }
        ]
    },
    {
        "statuses": [
            {
                "id": "3A0C810BBE72C289F9CD",
                "recipient_id": "19075550014",
                "status": "read",
                "timestamp": "1603408535",
                "conversation": {"id": "532b57b5f6e63595ccd74c6010e5c5c7"},
                "pricing": {"pricing_model": "CBP", "billable": False},
            }
        ]
    },
    {
        "statuses": [
            {
                "errors": [
                    {
                        "code": 470,
                        "title": "Failed to send message because you are outside the "
                        "support window for freeform messages to this user. Please use "
                        "a valid HSM notification or reconsider.",
                    }
                ],
                "id": "gBGGEgZHMlEfAgkM1RBkhDRr7t8",
                "recipient_id": "12064001000",
                "status": "failed",
                "timestamp": "1533332775",
            }
        ]
    },
    {
        "statuses": [
            {
                "errors": [
                    {
                        "code": 480,
                        "title": "Failed to send message since we detect an identity "
                        "change of the contact",
                    }
                ],
                "id": "gBGGFjFVU2AfAgldhhKwWDGSrTs",
                "recipient_id": "16315553601",
                "status": "failed",
                "timestamp": "1602535356",
            }
        ]
    },
    {
        "statuses": [
            {
                "id": "ABGGFmkiWVVPAgo66iFiii_-TG0-",
                "recipient_id": "16692259554",
                "status": "deleted",
                "timestamp": "1532413514",
            }
        ]
    },
    {
        "errors": [
            {
                "code": 400,
                "title": "Media download error",
                "details": "Failed to download the media from the sender.",
                "href": "location for error detail",
            },
        ]
    },
]

whatsapp_invalid = [
    {
        "contacts": [{}],
        "statuses": [
            {
                "id": "ABGGFmkiWVVPAgo66iFiii_-TG0-",
                "recipient_id": "16692259554",
                "status": "deleted",
                "timestamp": "1532413514",
            }
        ],
    },
    {"statuses": [{}]},
    {
        "statuses": [
            {
                "id": "ABGGFmkiWVVPAgo66iFiii_-TG0-",
                "recipient_id": "16692259554",
                "status": "foo",
                "timestamp": "1532413514",
            }
        ],
    },
    {
        "messages": [
            {
                "from": "16315551234",
                "id": "ABGGFlA5FpafAgo6tHcNmNjXmuSf",
                "timestamp": "1518694235",
                "type": "text",
            }
        ]
    },
    {
        "errors": [
            {
                "code": 400,
            }
        ]
    },
]


def test_whatsapp_valid():
    """
    All of the valid examples should validate
    """
    for data in whatsapp_valid:
        validate(data, whatsapp_webhook_schema)


def test_whatsapp_invalid():
    """
    All of the invalid examples should fail
    """
    cls = validator_for(whatsapp_webhook_schema)
    validator = cls(whatsapp_webhook_schema)
    for data in whatsapp_invalid:
        print(data)
        errors = list(validator.iter_errors(data))
        assert len(errors) > 0
