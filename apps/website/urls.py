from django.urls import path

from . import views

app_name = "website"

urlpatterns = [
    path("", views.home, name="home"),
    path("produtos/", views.product_list, name="product_list"),
    path("produtos/<slug:slug>/", views.product_detail, name="product_detail"),
    path("categorias/<slug:slug>/", views.category_detail, name="category_detail"),
]
