from django.conf import settings


def store(request):
    return {"WHATSAPP_NUMBER": settings.WHATSAPP_NUMBER}
