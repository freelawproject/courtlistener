import environ

env = environ.FileAwareEnv()

DISCLOSURE_HOST = env("DISCLOSURE_HOST", default="http://cl-disclosures:5050")
DOCTOR_HOST = env("DOCTOR_HOST", default="http://cl-doctor:5050")

MICROSERVICE_URLS = {
    # DOCTOR Endpoints
    "doctor-heartbeat": {
        "url": f"{DOCTOR_HOST}",
        "timeout": 5,
    },
    # Extractor Endpoints
    "document-extract": {
        "url": f"{DOCTOR_HOST}/extract/doc/text/",
        "timeout": 60 * 15,
    },
    "document-extract-ocr": {
        "url": f"{DOCTOR_HOST}/extract/doc/text/",
        "timeout": 60 * 90,
    },
    "recap-extract": {
        "url": f"{DOCTOR_HOST}/extract/recap/text/",
        "timeout": 60 * 90,
    },
    # Utils Endpoints
    "page-count": {
        "url": f"{DOCTOR_HOST}/utils/page-count/pdf/",
        "timeout": 120,
    },
    "audio-duration": {
        "url": f"{DOCTOR_HOST}/utils/audio/duration/",
        "timeout": 30,
    },
    "mime-type": {
        "url": f"{DOCTOR_HOST}/utils/mime-type/",
        "timeout": 60,
    },
    "buffer-extension": {
        "url": f"{DOCTOR_HOST}/utils/file/extension/",
        "timeout": 5,
    },
    "document-number": {
        "url": f"{DOCTOR_HOST}/utils/document-number/pdf/",
        "timeout": 60,
    },
    # Converter Endpoints
    "generate-thumbnail": {
        "url": f"{DOCTOR_HOST}/convert/pdf/thumbnail/",
        "timeout": 120,
    },
    "images-to-pdf": {
        "url": f"{DOCTOR_HOST}/convert/images/pdf/",
        "timeout": 60 * 10,
    },
    "convert-audio": {
        "url": f"{DOCTOR_HOST}/convert/audio/mp3/",
        "timeout": 60 * 60,
    },
    "downsize-audio": {
        "url": f"{DOCTOR_HOST}/convert/audio/ogg/",
        "timeout": 60 * 60,
    },
    # Disclosure Microservices
    "disclosure-heartbeat": {
        "url": f"{DISCLOSURE_HOST}",
        "timeout": 5,
    },
    "extract-disclosure": {
        "url": f"{DISCLOSURE_HOST}/extract/disclosure/",
        "timeout": 60 * 60 * 2,
    },
}
