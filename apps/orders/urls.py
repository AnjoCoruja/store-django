from django.urls import path

from . import views

app_name = "orders"

urlpatterns = [
    path("finalizar/", views.checkout, name="checkout"),
    path("<uuid:public_id>/planilha.xlsx", views.spreadsheet, name="spreadsheet"),
]
